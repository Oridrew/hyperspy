from operator import attrgetter
from hyperspy.misc.utils import attrsetter
from hyperspy.misc.export_dictionary import parse_flag_string

import numpy as np


def _slice_target(target, dims, both_slices, slice_nav=None, issignal=False):
    """Slices the target if appropriate

    Parameters
    ----------
    target : object
        Target object
    dims : tuple
        (navigation_dimensions, signal_dimensions) of the original object that
        is sliced
    both_slices : tuple
        (original_slices, array_slices) of the operation that is performed
    slice_nav : {bool, None}
        if None, target is returned as-is. Otherwise navigation and signal
        dimensions are sliced for True and False values respectively.
    issignal : bool
        if the target is signal and should be sliced as one
    """
    if slice_nav is None:
        return target
    if target is None:
        return None
    nav_dims, sig_dims = dims
    slices, array_slices = both_slices
    if slice_nav is True:  # check explicitly for safety
        if issignal:
            return target.inav[slices]
        if isinstance(target, np.ndarray):
            return np.atleast_1d(target[tuple(array_slices[:nav_dims])])
        raise ValueError(
            'tried to slice with navigation dimensions, but was neither a signal nor an array')
    if slice_nav is False:  # check explicitly
        if issignal:
            return target.isig[slices]
        if isinstance(target, np.ndarray):
            return np.atleast_1d(target[tuple(array_slices[-sig_dims:])])
        raise ValueError(
            'tried to slice with signal dimensions, but was neither a signal nor an array')
    # return thing


def copy_slice_from_whitelist(_from, _to, dims, both_slices, isNav):
    """Copies things from one object to another, according to whitelist, slicing
    where required.

    Parameters
    ----------
    _from : object
        Original object
    _to : object
        Target object
    dims : tuple
        (navigation_dimensions, signal_dimensions) of the original object that
        is sliced
    both_slices : tuple
        (original_slices, array_slices) of the operation that is performed
    isNav : bool
        if the slicing operation is performed on navigation dimensions of the
        object
    """

    def make_decision(flags, isnav):
        if isnav:
            if 'inav' in flags:
                return True
            return None
        if 'isig' in flags:
            return False
        return None

    for key, val in _from._whitelist.iteritems():
        if val is None:
            attrsetter(_to, key, attrgetter(key)(_from))
            continue
        flags_str, value = val
        flags = parse_flag_string(flags_str)
        if 'init' in flags:
            continue
        if 'id' in flags:
            continue
        if 'fn' in flags:
            attrsetter(_to, key, attrgetter(key)(_from))
            continue
        if 'inav' in flags or 'isig' in flags:
            thing = attrgetter(key)(_from)
            slice_nav = make_decision(flags, isNav)
            thing = _slice_target(
                thing,
                dims,
                both_slices,
                slice_nav,
                'sig' in flags)
            attrsetter(_to, key, thing)


class SpecialSlicers(object):

    def __init__(self, obj, isNavigation):
        self.isNavigation = isNavigation
        self.obj = obj

    def __getitem__(self, slices):
        return self.obj._slicer(slices, self.isNavigation)


class FancySlicing(object):

    def _get_array_slices(self, slices, isNavigation=None):
        try:
            len(slices)
        except TypeError:
            slices = (slices,)
        _orig_slices = slices

        has_nav = True if isNavigation is None else isNavigation
        has_signal = True if isNavigation is None else not isNavigation

        # Create a deepcopy of self that contains a view of self.data

        nav_idx = [el.index_in_array for el in
                   self.axes_manager.navigation_axes]
        signal_idx = [el.index_in_array for el in
                      self.axes_manager.signal_axes]

        if not has_signal:
            idx = nav_idx
        elif not has_nav:
            idx = signal_idx
        else:
            idx = nav_idx + signal_idx

        # Add support for Ellipsis
        if Ellipsis in _orig_slices:
            _orig_slices = list(_orig_slices)
            # Expand the first Ellipsis
            ellipsis_index = _orig_slices.index(Ellipsis)
            _orig_slices.remove(Ellipsis)
            _orig_slices = (_orig_slices[:ellipsis_index] + [slice(None), ] *
                            max(0, len(idx) - len(_orig_slices)) +
                            _orig_slices[ellipsis_index:])
            # Replace all the following Ellipses by :
            while Ellipsis in _orig_slices:
                _orig_slices[_orig_slices.index(Ellipsis)] = slice(None)
            _orig_slices = tuple(_orig_slices)

        if len(_orig_slices) > len(idx):
            raise IndexError("too many indices")

        slices = np.array([slice(None,)] *
                          len(self.axes_manager._axes))

        slices[idx] = _orig_slices + (slice(None),) * max(
            0, len(idx) - len(_orig_slices))

        array_slices = []
        for slice_, axis in zip(slices, self.axes_manager._axes):
            if (isinstance(slice_, slice) or
                    len(self.axes_manager._axes) < 2):
                array_slices.append(axis._get_array_slices(slice_))
            else:
                if isinstance(slice_, float):
                    slice_ = axis.value2index(slice_)
                array_slices.append(slice_)
        return array_slices

    def _slicer(self, slices, isNavigation=None):
        array_slices = self._get_array_slices(slices, isNavigation)
        _obj = self._deepcopy_with_new_data(self.data[array_slices])
        for slice_, axis in zip(array_slices, _obj.axes_manager._axes):
            if (isinstance(slice_, slice) or
                    len(self.axes_manager._axes) < 2):
                axis._slice_me(slice_)
            else:
                _obj._remove_axis(axis.index_in_axes_manager)
        if hasattr(self, "_additional_slicing_targets"):
            for ta in self._additional_slicing_targets:
                try:
                    t = attrgetter(ta)(self)
                    if hasattr(t, '_slicer'):
                        attrsetter(
                            _obj,
                            ta,
                            t._slicer(
                                slices,
                                isNavigation))
                except AttributeError:
                    pass
        _obj.get_dimensions_from_data()

        return _obj

# vim: textwidth=80
