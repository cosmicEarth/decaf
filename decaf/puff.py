"""Puff defines a purely unformatted file format accompanying decaf for easier
and faster access of numpy arrays.
"""
import cPickle as pickle
import numpy as np
from operator import mul

class Puff(object):
    """The puff class. It defines a simple interface that stores numpy arrays in
    its raw form.
    """
    def __init__(self, name, start = None, end = None):
        """Initializes the puff object.

        Input:
            name: the puff filename to be read.
            start: (optional) the local range start.
            end: (optional) the local range end.
        """
        if name.endswith('.puff'):
            name = name[:-5]
        # shape is the shape of a single data point.
        self._shape = None
        # step is an internal variable that indicates how many bytes we need
        # to jump over per data point
        self._step = None
        # num_data is the total number of data in the file
        self._num_data = None
        # the following variables are used to slice a puff
        self._start = None
        self._end = None
        # the current index of the data.
        self._curr = None
        # the number of local data
        self._num_local_data = None
        # dtype is the data type of the data
        self._dtype = None
        # iter_count is used to record the iteration status 
        self._iter_count = 0
        # the fid for the opened file
        self._fid = None
        self.open(name)
        self.set_range(start, end)


    def set_range(self, start, end):
        """sets the range that we will read data from."""
        if start is not None:
            if start > self._num_data:
                raise ValueError('Invalid start index.')
            else:
                self._start = start
                self.seek(self._start)
                self._curr = self._start
        if end is not None:
            if end > start and end <= self._num_data:
                self._end = end
            else:
                raise ValueError('Invalid end index.')
        self._num_local_data = self._end - self._start

    def reset(self):
        """Reset the puff pointer to the start of the local range."""
        self.seek(self._start)

    def __iter__(self):
        """A simple iterator to go through the data."""
        self.seek(self._start)
        self._iter_count = 0
        return self

    def next(self):
        """The next function."""
        if self._curr == self._start and self._iter_count:
            raise StopIteration
        else:
            self._iter_count += 1
            return self.read(1)[0]

    def num_data(self):
        """Return the number of data."""
        return self._num_data
    
    def shape(self):
        """Return the shape of a single data point."""
        return self._shape

    def dtype(self):
        """Return the dtype of the data."""
        return self._dtype

    def num_local_data(self):
        """Returns the number of local data."""
        return self._num_local_data

    def open(self, name):
        """Opens a puff data: it is composed of two files, name.puff and
        name.icing. The open function will set the range to all the data
        points - use set_range() to specify a custom range to read from.
        """
        icing = pickle.load(open(name + '.icing'))
        self._shape = icing['shape']
        self._dtype = icing['dtype']
        self._num_data = icing['num']
        self._step = reduce(mul, self._shape, 1)
        self._fid = open(name + '.puff', 'rb')
        self._start = 0
        self._end = self._num_data
        self._num_local_data = self._num_data
        self._curr = 0

    def seek(self, offset):
        """Seek to the beginning of the offset-th data point."""
        if offset < self._start or offset >= self._end:
            raise ValueError('Offset should lie in the data range.')
        self._fid.seek(offset * self._step * self._dtype.itemsize)
        self._curr = offset

    def read(self, count):
        """Read the specified number of data and return as a numpy array."""
        if count > self._num_local_data:
            raise ValueError('Not enough data points to read: count %d, limit'
                             ' %d.' % (count, self._num_local_data))
        if self._curr + count <= self._end:
            data = np.fromfile(self._fid, self._dtype, count * self._step)
            self._curr += count
            if self._curr == self._end:
                # When everything is read, we restart from the head.
                self.seek(self._start)
        else:
            part = self._end - self._curr
            data = np.vstack((self.read(part),
                              self.read(count - part)))
        return data.reshape((count,) + self._shape)

    def read_all(self):
        """Reads all the data from the file."""
        self.seek(self._start)
        return self.read(self._num_local_data)


class PuffStreamedWriter(object):
    """A streamed writer to write a large puff incrementally."""
    def __init__(self, name):
        self._shape = None
        self._num_data = 0
        self._dtype = None
        self._fid = open(name + '.puff', 'wb')
        self._name = name
    
    def check_validity(self, arr):
        """Checks if the data is valid."""
        if self._shape is None:
            self._shape = arr.shape
            self._dtype = arr.dtype
        else:
            if self._shape != arr.shape or self._dtype != arr.dtype:
                raise TypeError('Array invalid with previous inputs! '
                                'Previous: %s, %s, current: %s %s' %
                                (str(self._shape), str(self._dtype),
                                 str(arr.shape), str(arr.dtype)))

    def write_single(self, arr):
        """Write a single data point."""
        self.check_validity(arr)
        arr.tofile(self._fid)
        self._num_data += 1

    def write_batch(self, arr):
        """Write a bunch of data points to file."""
        self.check_validity(arr[0])
        arr.tofile(self._fid)
        self._num_data += arr.shape[0]

    def finish(self):
        """Finishes a Puff write."""
        if self._num_data == 0:
            raise ValueError('Nothing is written!')
        self._fid.close()
        with open(self._name + '.icing', 'w') as fid:
            pickle.dump({'shape': self._shape,
                         'dtype': self._dtype,
                         'num': self._num_data}, fid)

def write_puff(arr, name):
    """Write a single numpy array to puff format."""
    writer = PuffStreamedWriter(name)
    writer.write_batch(arr)
    writer.finish()

def merge_puff(names, output_name, batch_size=None):
    """Merges a set of puff files, sorted according to their name.
    Input:
        names: a set of file names to be merged. The order does not matter,
            but note that we will sort the names internally.
        output_name: the output file name.
        batch_size: if None, read the whole file and write it in a single
            batch. Otherwise, read and write the given size at a time.
    """
    names.sort()
    writer = PuffStreamedWriter(output_name)
    if batch_size is None:
        for name in names:
            writer.write_batch(Puff(name).read_all())
    else:
        for name in names:
            puff = Puff(name)
            num = puff.num_data()
            for curr in range(0, num, batch_size):
                writer.write_batch(puff.read(batch_size))
            # write the last batch
            writer.write_batch(puff.read(num - curr))
    # Finally, finish the write.
    writer.finish()

def puffmap(func, puff, output_name, write_batch=None):
    """A function similar to map() that runs the func on each item of the puff
    and writes the result to output_name.
    Input:
        func: a function that takes in a puff entry and returns a numpy array.
        puff: the puff file. May be locally sliced.
        output_name: the output puff file name.
        write_batch: if True, we will use write_batch() instead of
            write_single(). This may be useful when each input puff element
            leads to multiple output elements. Default False.
    """
    writer = PuffStreamedWriter(output_name)
    if write_batch:
        for elem in puff:
            writer.write_batch(func(elem))
    else:
        for elem in puff:
            writer.write_single(func(elem))
    writer.finish()
