"""Implements the inner product layer."""

from decaf import base
import numpy as np

class FlattenLayer(base.Layer):
    """A layer that flattens the data to a 1-dim vector (the resulting
    minibatch would be a 2-dim matrix."""

    def __init__(self, **kwargs):
        """Initializes a ReLU layer.
        """
        base.Layer.__init__(self, **kwargs)
    
    def forward(self, bottom, top):
        """Computes the forward pass."""
        for blob_b, blob_t in zip(bottom, top):
            shape = blob_b.data().shape
            newshape = (shape[0], np.prod(shape[1:]))
            blob_t.mirror(blob_b, shape=newshape)

    def backward(self, bottom, top, propagate_down):
        """Computes the backward pass."""
        if not propagate_down:
            return 0.
        for blob_b, blob_t in zip(bottom, top):
            shape = blob_t.diff().shape
            newshape = (shape[0], np.prod(shape[1:]))
            blob_b.mirror_diff(blob_t, shape=newshape)

    def update(self):
        """FlattenLayer has nothing to update."""
        pass
