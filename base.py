"""base.py implements the basic data types.
"""

import cPickle as pickle
from collections import defaultdict
import gzip
import logging
import networkx as nx
import numpy as np


class DecafError(Exception):
    """NOOOOOOO! I need caffeine!
    
    Yes, this is the basic error type under decaf.
    """
    pass


class InvalidLayerError(DecafError):
    """The error when an invalid spec is passed to a layer."""
    pass


class InvalidNetError(DecafError):
    """The error raised when the network does not pass validation."""
    pass


class Filler(object):
    """This is the class that implements util functions to fill a blob.
    
    A filler implements the fill() function that takes a blob as the input,
    and fills the blob's data() field.
    """

    def __init__(self, **kwargs):
        """simply get the spec."""
        self.spec = kwargs

    def fill(self, mat):
        raise NotImplementedError


# pylint: disable=R0903
class Blob(object):
    """Blob is the data structure that holds a piece of numpy array as well as
    its gradient so that we can accumulate and pass around data more easily.

    We define two numpy matrices: one is data, which stores the data in the
    current blob; the other is diff (short for difference): when a network
    runs its forward and backward pass, diff will store the gradient value;
    when a solver goes through the blobs, diff will then be replaced with the
    value to update.

    The diff matrix will not be created unless you explicitly run init_diff,
    as many Blobs do not need the gradients to be computed.
    """
    def __init__(self, shape=None, dtype=np.float64, filler=None):
        self._data = None
        self._diff = None
        self._filler = filler
        if shape is not None:
            self.init_data(shape, dtype)

    def clear(self):
        """Clears a blob data."""
        self._data = None
        self._diff = None

    def mirror(self, input_array, shape=None):
        """Create the data as a view of the input array. This is useful to
        save space and avoid duplication for data layers.
        """
        if isinstance(input_array, Blob):
            self._data = input_array.data()
        else:
            self._data = input_array.view()
        if shape is not None:
            self._data.shape = shape
   
    def mirror_diff(self, input_array, shape=None):
        """Create the diff as a view of the input array's diff. This is useful
        to save space and avoid duplication for data layers.
        """
        if isinstance(input_array, Blob):
            self._diff = input_array.diff()
        else:
            self._diff = input_array.view()
        if shape is not None:
            self._diff.shape = shape

    def has_data(self):
        """Checks if the blob has data."""
        return self._data is not None
    
    def data(self):
        """Returns a view of the data."""
        return self._data.view()

    def has_diff(self):
        """Checks if the blob has diff."""
        return self._diff is not None

    def diff(self):
        """Returns the diff."""
        return self._diff.view()

    def update(self):
        """Update the data field by SUBTRACTING diff to it.
        
        Note that diff is often used to store the gradients, and most often
        we will perform MINIMIZATION. This is why we always do subtraction
        here.
        """
        self._data -= self._diff

    def init_data(self, shape, dtype=np.float64):
        """Initializes the data if necessary. The filler will be always
        called even if no reallocation of data takes place.
        """
        if self.has_data() and self._data.shape == shape and \
           self._data.dtype == dtype:
            self._data[:] = 0
        else:
            self._data = np.zeros(shape, dtype)
        if self._filler is not None:
            self._filler.fill(self._data)
        return self.data()

    def init_diff(self):
        """Initialize the diff in the same format as data.
        
        Returns diff for easy access.
        """
        if not self.has_data():
            raise ValueError('The data should be initialized first!')
        if self.has_diff() and self._diff.shape == self._data.shape and \
           self._diff.dtype == self._data.dtype:
            self._diff[:] = 0
        else:
            self._diff = np.zeros(self._data.shape, self._data.dtype)
        return self.diff()
    
    def __getstate__(self):
        """When pickling, we will not store the diff field."""
        dictionary = dict(self.__dict__)
        dictionary['_diff'] = None
        return dictionary


class Layer(object):
    """A Layer is the most basic component in decal. It takes multiple blobs
    as its input, and produces its outputs as multiple blobs. The parameter
    to be learned in the layers are 
    
    When designing layers, always make sure that your code deals with minibatches.
    """

    def __init__(self, **kwargs):
        """Creates a Layer.

        Necessary argument:
            name: the name of the layer.
        """
        self.spec = kwargs
        self.name = self.spec['name']
        self.freeze = self.spec.get('freeze', False)
        self._param = []

    def forward(self, bottom, top):
        """Computes the forward pass.
        
        Input:
            bottom: the data at the bottom.
            top: the top-layer output.
        """
        raise NotImplementedError

    def backward(self, bottom, top, propagate_down):
        """Computes the backward pass.
        Input:
            bottom: the data at the bottom.
            top: the data at the top.
            propagate_down: if set False, the gradient w.r.t. the bottom
                blobs does not need to be computed.
        Output:
            loss: the loss being generated in this layer. Note that if your
                layer does not generate any loss, you should still return 0.
        """
        raise NotImplementedError
    
    def update(self):
        """Updates my parameters, based on the diff value given in the param
        blob.
        """
        raise NotImplementedError

    def param(self):
        """Returns the parameters in this layer. It should be a list of
        Blob objects.
        
        In our layer, either collect all your parameters into the self._param
        list, or implement your own param() function.
        """
        return self._param


# pylint: disable=R0921
class DataLayer(Layer):
    """A Layer that generates data.
    """
    
    def forward(self, bottom, top):
        """Generates the data.
        
        Your data layer should override this function.
        """
        raise NotImplementedError

    def backward(self, bottom, top, propagate_down):
        """No gradient needs to be computed for data.
        
        You should not override this function.
        """
        raise DecafError('You should not reach this.')

    def update(self):
        """The data layer has no parameter, and the update() function
        should not be called.
        """
        pass


# pylint: disable=R0921
class LossLayer(Layer):
    """A Layer that implements loss. Usually, the forward pass of the loss
    does the actual computation of both the loss and the gradients, and the
    backward pass will simply return the loss value. The loss layer should not
    accept any blobs on its top.
    
    The loss layer takes a keyword argument 'weight' (defaults to 1) that
    allows one to adjust the balance between multiple losses.
    """

    def __init__(self, **kwargs):
        Layer.__init__(self, **kwargs)
        self._loss = 0
        self.spec['weight'] = self.spec.get('weight', 1.)

    def forward(self, bottom, top):
        """The forward pass. In your loss layer, you need to compute the loss
        and store it at self._loss.
        """
        raise NotImplementedError

    def backward(self, bottom, top, propagate_down):
        return self._loss

    def update(self):
        pass


class SplitLayer(Layer):
    """A layer that splits a blob to multiple blobs."""

    def __init__(self, **kwargs):
        """Initializes a Split layer.
        """
        Layer.__init__(self, **kwargs)
    
    def forward(self, bottom, top):
        """Computes the forward pass.

        The output will simply mirror the input data.
        """
        if len(bottom) != 1:
            raise ValueError(
                'SplitLayer only accepts one input as its bottom.')
        for output in top:
            output.mirror(bottom[0])

    def backward(self, bottom, top, propagate_down):
        """Computes the backward pass."""
        if propagate_down:
            diff = bottom[0].init_diff()
            for single_top in top:
                diff[:] += single_top.diff()
        return 0.

    def update(self):
        """Split has nothing to update."""
        pass


class Solver(object):
    """This is the very basic form of the solver."""
    def __init__(self, **kwargs):
        self.spec = kwargs

    def solve(self, net):
        """The solve function takes a net as an input, and optimizes its
        parameters.
        """
        raise NotImplementedError


class Regularizer(object):
    """This is the class that implements the regularization terms.
    
    A regularizer takes in a blob and a scale term, and adds the gradient
    imposed by the regularization term to the blob's diff() field. It then
    returns the 
    """

    def __init__(self, **kwargs):
        """Initializes a regularizer. A regularizer needs a necessary keyword
        'weight'.
        """
        self.spec = kwargs
        self._weight = self.spec['weight']

    def reg(self, blob):
        """Compute the regularization term from the blob's data field, and
        add the regularization term to its diff directly.

        Input:
            blob: the blob to work on.
        """
        raise NotImplementedError


_DECAF_INSERTED_PREFIX = '_decaf'


class Net(object):
    """A Net is a directed graph with layer names and layer instances."""

    def __init__(self, name=None):
        """Initialize a net.
        Input:
            name: (optional) a string to help remember what the net does.
        """
        if name is None:
            name = 'decaf_net'
        self.name = name
        self._graph = nx.DiGraph()
        self.blobs = {}
        # layers is a dictionary that maps layer names to actual layers.
        self.layers = {}
        # needs is a dictionary that maps layer names to a list of blob names
        # that it needs.
        self._needs = {}
        # provides is a dictionary that maps layer names to a list of blob
        # names that it provides.
        self._provides = {}
        # The parameters below will be automaticall inferred 
        # The counts for blobs
        self._need_count = defaultdict(int)
        # The topological order to execute the layer.
        self._forward_order = None
        self._backward_order = None
        # input_blobs are all blobs that have no layer producing them - they
        # have to be provided by the user. We only store the blob names.
        self._input_blobs = None
        # output_blibs are all blobs that no layer uses - they will be emitted
        # by the predict() function. We only store the blob names.
        self._output_blobs = None
        self._params = None
        self._finished = False

    def save(self, filename, protocol=0, store_full=False):
        """Saving the necessary 
        
        When pickling, we will simply store the network structure, but not
        any of the inferred knowledge or intermediate blobs.
        
        data layers and loss layers. If store_full is False, the data and loss
        layers are stripped and not stored - this will enable one to just keep
        necessary layers for future use.
        """
        output = [self.name, {}]
        for name, layer in self.layers.iteritems():
            if (not store_full and
                (isinstance(layer, DataLayer) or 
                 isinstance(layer, LossLayer) or
                 name.startwith(_DECAF_INSERTED_PREFIX))):
                # We do not need to store these layers.
                continue
            else:
                output[1][name] = (layer, self._needs[name], self._provides[name])
        # finally, pickle the content.
        file = gzip.open(filename, 'wb')
        pickle.dump(output, file, protocol=protocol)

    @staticmethod
    def load(filename):
        """Loads a network from file."""
        self = Net()
        file = gzip.open(filename, 'rb')
        contents = pickle.load(file)
        self.name = contents[0]
        for layer, needs, provides in contents[1].values():
            self.add_layer(layer, needs=needs, provides=provides)
        self.finish()
        return self

    def load_from(self, filename):
        """Load the parameters from an existing network.

        Unlike load, this function should be called on an already constructed
        network. What it does is to look into the file, and if there is any
        layer in the file that has the same name as a layer name defined in
        the current network, replace the current network's corresponding layer
        with the layer in the file.
        """
        file = gzip.open(filename, 'rb')
        contents = pickle.load(file)
        for name in contents[1]:
            if name in self.layers:
                self.layers[name] = contents[1][name][0]
        # after loading, we need to re-parse the layer to fix all reference
        # issues.
        self.finish()


    def add_layer(self, layer, needs=None, provides=None):
        """Add a layer to the current network.

        Args:
            layer: a decaf.base.Layer instance.
            needs: a tuple of strings, indicating the blobs that the layer
                needs as its input.
            provides: similar to needs, but the layer's output instead.
        """
        # validate input
        if needs is None:
            needs = []
        if provides is None:
            provides = []
        if type(needs) is str:
            needs = [needs]
        if type(provides) is str:
            provides = [provides]
        self._finished = False
        # Add the layer
        if layer.name in self.layers or layer.name in self.blobs:
            raise InvalidNetError('A name already exists: %s' % layer.name)
        self.layers[layer.name] = layer
        # Add the blobs
        for blobname in provides:
            if blobname in self.blobs:
                raise InvalidNetError(
                    'Blob %s already provided by another layer.' % blobname)
        for blobname in needs + provides:
            if blobname in self.layers:
                raise InvalidNetError(
                    'Blob name found as a layer name: %s' % blobname)
            elif blobname not in self.blobs:
                self.blobs[blobname] = Blob()
        #TODO: fix (this is not finished but it is too late)
        for name in needs: 
            self._need_count[name] += 1
        self._needs[layer.name] = list(needs)
        self._provides[layer.name] = list(provides)
        self._actual_needs = None
    
    def finish(self):
        """Call this function when you finish the network construction."""
        # validate and generate the graph
        self._generate_graph()
        try:
            topological_order = nx.topological_sort(self._graph)
        except nx.NetworkXUnfeasible as error:
            raise DecafError(error)
        # For efficiency reasons, we will see for each layer, whether the
        # backward operation needs to be carried out.
        # This is stored in two parameters:
        #   need_backward: whether the backward pass needs to be carried out.
        #   propagate_down: whether the gradient w.r.t. to the bottom layer
        #       needs to be carried out.
        for name in topological_order:
            # whether the predecessor needs backward operation.
            pred_need_backward = any(self._graph.node[p]['need_backward']
                                     for p in self._graph.predecessors(name))
            if name in self.layers:
                # see if a layer needs backward operation. A layer needs
                # backward operation if (1) it has parameters and isn't frozen
                # or (2) any of its predecessors needs backward operation.
                layer = self.layers[name]
                if (pred_need_backward or
                    (len(layer.param()) and not layer.freeze)):
                    self._graph.node[name]['need_backward'] = True
                else:
                    self._graph.node[name]['need_backward'] = False
                # see if a layer needs to compute its bottom diff. A layer
                # needs to compute its bottom diff if any of its predecessors
                # needs backward operation.
                if pred_need_backward:
                    self._graph.node[name]['propagate_down'] = True
                else:
                    self._graph.node[name]['propagate_down'] = False
            else:
                # see if a blob needs backward operation.
                # This is only used so we can verify further layers.
                self._graph.node[name]['need_backward'] = pred_need_backward
        # create the order to run forward and backward passes
        layerorder = [name for name in topological_order
                      if name in self.layers]
        logging.info('Layer order: %s', str(layerorder))
        self._forward_order = []
        for n in layerorder:
            self._forward_order.append(
                (n, self.layers[n],
                 [self.blobs[name] for name in self._actual_needs[n]],
                 [self.blobs[name] for name in self._provides[n]]))
        logging.info('Forward layer details: %s', str(self._forward_order))
        self._backward_order = []
        for n in layerorder[::-1]:
            if self._graph.node[n]['need_backward']:
                self._backward_order.append(
                    (n, self.layers[n],
                     [self.blobs[name] for name in self._needs[n]],
                     [self.blobs[name] for name in self._provides[n]],
                     self._graph.node[n]['propagate_down']))
        logging.info('Backward layer details: %s', str(self._backward_order))
        # store all the parameters
        self._params = []
        for name in layerorder:
            self._params.extend(self.layers[name].param())
        # Note: Any further finishing code should be inserted here.
        self._finished = True
    
    def params(self):
        """Return a list of parameters used in the network."""
        return self._params

    def _generate_graph(self):
        """Validates if a network is executable, and generates the networkx 
        graph that reflects the execution order.
        """
        # first, get input and output blobs.
        provided_blobs = set(sum(self._provides.values(), []))
        self._input_blobs = [name for name in self.blobs
                             if name not in provided_blobs]
        if len(self._input_blobs):
            logging.info('This layer needs input blobs: %s',
                         str(self._input_blobs))
        self._output_blobs = [name for name in self.blobs
                              if name not in self._need_count]
        if len(self._output_blobs):
            logging.info('This layer produces output blobs: %s',
                         str(self._output_blobs))
        # TODO: get the actual needs and provides maps.
        # For any blob that is needed by multiple layers, we will insert a split
        # layer to avoid gradient overwriting.
        for name, count in self._need_count.iteritems:
            if count > 1:
                split_provides = ['_'.join(_DECAF_INSERTED_PREFIX, name, str(i))
                                  for i in range(count)]
                self.add_layer(SplitLayer(name=_DECAF_INSERTED_PREFIX + name),
                               needs=[name],
                               provides=split_provides)
        # compute actual_needed
        temp_need_idx = defaultdict(int)
        for layername, blobnames in self._needs:
            actual_needs = []
            for blobname in blobnames:
                if self._need_count[blobname] > 1:
                    # instead of connecting it to the original blob, we connect
                    # it to the new splitted blob.
                    actual_needs.append('_'.join(_DECAF_INSERTED_PREFIX, name,
                                                 temp_need_idx[blobname]))
                    temp_need_idx[blobname] += 1
                else:
                    actual_needs.append(blobname)
            self._actual_needs[layername] = actual_needs
        # Now, create the graph
        self._graph = nx.DiGraph()
        for layername, blobnames in self._actual_needs:
            for blobname in blobnames:
                self.graph.add_edge(blobname, layername)
        for layername, blobname in self._provides:
            self.graph.add_edge(layername, blobname)
        # Done creating graph!
        return        
                        
    def forward_backward(self, previous_net = None):
        """Runs the forward and backward passes of the net.
        """
        # the forward pass. We will also accumulate the loss function.
        if not self._finished:
            # Trying to modify an already finished network.
            raise DecafError('Call finish() before you use the network.')
        if len(self._input_blobs):
            raise DecafError('Cannot run forward_backward on a network with'
                             ' input blobs. Did you mean predict()?')
        if len(self._output_blobs):
            # If the network has output blobs, it usually shouldn't be used
            # to run forward-backward: such blobs won't be used and cause waste
            # of computation. Maybe the user is missing a few loss layers? We
            # will print the warning but still carry on.
            logging.warning('Have multiple unused blobs in the net. Do you'
                            ' actually mean running a forward backward pass?')
        loss = 0.
        for _, layer, bottom, top in self._forward_order:
            layer.forward(bottom, top)
        # the backward pass
        for name, layer, bottom, top, propagate_down in self._backward_order:
            layer_loss = layer.backward(bottom, top, propagate_down)
            if layer_loss > 0:
                logging.debug('layer %s produces loss %f.', name, layer_loss)
            loss += layer_loss
        return loss

    def predict(self, **kwargs):
        """Use the network to perform prediction. Note that your network
        should have at least one output blob. All input blobs need to be
        provided using the kwargs.
        """
        for name, arr in kwargs.iteritems():
            self.blobs[name].mirror(arr)
        for _, layer, bottom, top in self._forward_order:
            layer.forward(bottom, top)
        return dict([(name, self.blobs[name].data())
                     for name in self._output_blobs])

    def update(self):
        """Update the parameters using the diff values provided in the
        parameters blob."""
        for _, layer in self.layers.iteritems():
            layer.update()
