"""
Module used to define H5 queries.
"""
from __future__ import print_function
import io

import tables
import numpy as np

try:
    import matplotlib.pyplot as plt
    plt.ioff()
except ImportError:
    plt = None


def plot(x, y, xlabel, ylabel, title='', image_type="png", **kwargs):
    """
    Plots the given numpy array in pyplot (in the given format) and
    returns the image

    Parameters
    ----------
    x : array-like
        X values.
    y : array-like
        Y values.
    title : str, optional
        Title of plot.
    image_type : str, optional
        Format of image to be returned.
    **kwargs
        Keyword arguments for ``plt.plot``.

    Returns
    -------
    out : io.BytesIO
        Image in the format of image_type.
    """
    if plt is None:
        raise ValueError('Please install matplotlib')

    plt.plot(x, y, **kwargs)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    buf = io.BytesIO()
    plt.savefig(buf, format=image_type)
    buf.seek(0)
    plt.close()
    return buf


def plot_heatmap(data, vmin, vmax, hmin, hmax, title='HeatMap for Sample',
                 image_type='png', **kwargs):
    """
    Plots the given numpy array in pyplot on a log scale (in the given format)
    and returns the image.

    Parameters
    ----------
    data : dict
        Dictionary returned by get_HeatMapRTMZ.
    vmin : int
        Minimum index along the mz axis.
    vmax : int
        Maximum index along the mz axis.
    hmin : int
        Minimum index along the rt axis.
    hmax : int
        Maximum index along the rt axis.
    title : str, optional
        Title of plot.
    image_type : str, optional
        Format of image to be returned.
    **kwargs
        Keyword arguments for ``plt.imshow``.  Can also specify the "name" of
        the sample for the title.

    Returns
    -------
    out : io.BytesIO
        Image in the format of image_type.
    """
    if plt is None:
        raise ValueError('Please install matplotlib')

    kwargs.setdefault('interpolation', 'nearest')
    kwargs.setdefault('aspect', 'auto')
    kwargs.setdefault('cmap', 'YlGnBu_r')

    arr = data['data'][vmin: vmax, hmin: hmax]
    hmin *= data['rt_step']
    hmax *= data['rt_step']
    vmin *= data['mz_step']
    vmax *= data['mz_step']

    kwargs['extent'] = [hmin, hmax, vmax, vmin]

    plt.imshow(arr, **kwargs)
    plt.xlabel('Time (min)')
    plt.ylabel('M/Z')
    plt.title(title)
    plt.colorbar()

    buf = io.BytesIO()
    plt.savefig(buf, format=image_type)
    buf.seek(0)
    plt.close()
    return buf


def get_data(h5file, ms_level, polarity, **kwargs):
    """
    Get data from an h5file meeting given criteria.

    Parameters
    ----------
    ms_level : int
        MS Level.
    polarity : int
        Plus proton (1) or Minus proton (0).
    **kwargs
        Optional search modifiers.  (e.g. min_r=0, max_mz=100, precursor_MZ=1)

    Returns
    -------
    out : dictionary
        Dictionary with arrays for 'i', 'mz', and 'rt' values meeting criteria.
    """
    query = '(ms_level == %s) & (polarity == %s)' % (ms_level, polarity)

    for name in ['rt', 'mz', 'precursor_MZ', 'precursor_intensity',
                 'collision_energy']:
        if 'min_%s' % name in kwargs:
            query += ' & (%s >= %s)' % (name, kwargs['min_%s' % name])
        if 'max_%s' % name in kwargs:
            query += ' & (%s <= %s)' % (name, kwargs['max_%s' % name])
        if name in kwargs:
            query += ' & (%s == %s)' % (name, kwargs[name])

    print('Querying: %s' % query)

    table = h5file.root.spectra
    i = np.array([x['i'] for x in table.where(query)])
    rt = np.array([x['rt'] for x in table.where(query)])
    mz = np.array([x['mz'] for x in table.where(query)])

    return dict(i=i, rt=rt, mz=mz)


def get_XIC(h5file, min_mz, max_mz, ms_level, polarity, bins=None, **kwargs):
    """
    Get Extracted-ion chromatogram (XIC) data - RT vs. cum sum of intensities

    Parameters
    ----------
    h5file : table file handle
        Handle to an open tables file.
    min_mz : float
        Minimum m/z value.
    max_mz : float
        Maximum m/z value.
    ms_level : int
        MS Level.
    polarity: int
        Plus proton (1) or Minus proton (0).
    bins : int or array-like, optional.
        Desired bins to use for the histogram.  By default, aggregates by
        retention time.
    **kwargs
        Optional search modifiers.  (e.g. precursor_MZ=1,
            min_collision_energy=4)

    Returns
    -------
    out : tuple of arrays
        (rt_vals, i_vals) arrays in the desired range.
    """
    data = get_data(h5file, ms_level, polarity, min_mz=min_mz,
                    max_mz=max_mz, **kwargs)

    if bins:
        i, rt = np.histogram(data['rt'], bins=bins, weights=data['i'])
        # center the bins
        rt = (rt[:-1] + rt[1:]) / 2

    else:
        # combine the data within each retention time step
        jumps = np.nonzero(np.diff(data['rt']))[0]
        jumps = np.hstack((0, jumps, data['rt'].size - 1))

        isum = np.cumsum(data['i'])

        i = np.diff(np.take(isum, jumps))
        i[0] += data['i'][0]
        rt = np.take(data['rt'], jumps)[1:]

    return rt, i


def get_HeatMapRTMZ(h5file, mz_bins, rt_bins, ms_level, polarity, **kwargs):
    """
    Get a HeatMap of RT vs MZ.

    Parameters
    ----------
    h5file : table file handle
        Handle to an open tables file.
    mz_steps : int or array-like
        Bins to use for the mz axis.
    rt_steps : int or array-like
        Bins to use for the rt axis.
    ms_level : int
        MS Level.
    polarity: int
        Plus proton (1) or Minus proton (0).
    **kwargs
        Optional search modifiers.  (e.g. precursor_MZ=1,
            min_collision_energy=4)

    Returns
    -------
    out : dict
        Dictionary containing: 'arr', 'rt_bins', 'mz_bins'
    """
    data = get_data(h5file, ms_level, polarity, **kwargs)

    arr, mz_bins, rt_bins = np.histogram2d(data['mz'], data['rt'],
                                           weights=data['i'],
                                           bins=(mz_bins, rt_bins))

    # center the bins
    mz_bins = (mz_bins[:-1] + mz_bins[1:]) / 2
    rt_bins = (rt_bins[:-1] + rt_bins[1:]) / 2

    return dict(arr=arr, rt_bins=rt_bins, mz_bins=mz_bins)


def get_spectragram(h5file, min_rt, max_rt, ms_level, polarity,
                    bins=2000, **kwargs):
    """
    Get cumulative I vs MZ in RT Range (Spectragram)

    Parameters
    ----------
    h5file : table file handle
        Handle to an open tables file.
    min_rt : float
        Minimum retention time.
    max_rt : float
        Maximum retention time.
    ms_level : int
        MS Level.
    polarity: int
        Plus proton (1) or Minus proton (0).
    bins : int or array-like
        Desired bins for the histogram.
    **kwargs
        Optional search modifiers.  (e.g. precursor_MZ=1,
            min_collision_energy=4)

    Returns
    -------
    out : tuple of arrays
        (mz_vals, i_vals) arrays in the desired range.
    """
    data = get_data(h5file, ms_level, polarity, min_rt=min_rt,
                    max_rt=max_rt, **kwargs)

    i, mz = np.histogram(data['mz'], bins=bins, weights=data['i'])
    # center the bins
    mz = (mz[:-1] + mz[1:]) / 2

    return (mz, i)


if __name__ == '__main__':  # pragma: no cover
    import sys

    fid = tables.open_file('test.h5')

    if len(sys.argv) < 2 or sys.argv[1] == 'xic':
        x, y = get_XIC(fid, 1, 1000, 1, 0)
        np.save('xicof_new.npy', np.vstack((x, y)).T)
        plt.plot(x, y)

    elif sys.argv[1] == 'ivsmz':
        x, y = get_spectragram(fid, 1, 5, 1, 0)
        np.save('ivsmz_new.npy', np.vstack((x, y)).T)
        plt.plot(x, y)

    else:
        data = get_HeatMapRTMZ(fid, 1000, 1000, 1, 0)
        data = (data['data'] + 1) ** 0.1
        np.save('heatmap_new.py', data)
        plt.imshow(data)

    plt.show()
