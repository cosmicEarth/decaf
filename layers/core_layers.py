# pylint: disable=W0611
"""Imports commonly used layers."""

# Utility layers
from decaf.base import SplitLayer

# Data Layers
from decaf.layers.data.ndarraydata import NdarrayDataLayer
from decaf.layers.data.cifar import CIFARDataLayer
from decaf.layers.data.mnist import MNISTDataLayer
from decaf.layers.sampler import (BasicMinibatchLayer,
                                  RandomPatchLayer)

# Computation Layers
from decaf.layers.convolution import ConvolutionLayer
from decaf.layers.group_convolution import GroupConvolutionLayer
from decaf.layers.deconvolution import DeconvolutionLayer
from decaf.layers.dropout import DropoutLayer
from decaf.layers.flatten import FlattenLayer
from decaf.layers.im2col import Im2colLayer
from decaf.layers.innerproduct import InnerProductLayer
from decaf.layers.loss import (SquaredLossLayer,
                               MultinomialLogisticLossLayer,
                               AutoencoderLossLayer)
from decaf.layers.normalize import (MeanNormalizeLayer,
                                    ResponseNormalizeLayer,
                                    LocalResponseNormalizeLayer)
from decaf.layers.padding import PaddingLayer
from decaf.layers.pooling import PoolingLayer
from decaf.layers.relu import ReLULayer
from decaf.layers.sigmoid import SigmoidLayer

