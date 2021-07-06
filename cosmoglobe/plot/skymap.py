from cosmoglobe.utils.utils import ModelError
from logging import error
from cosmoglobe.sky.components import Component
from cosmoglobe.sky.model import Model

import warnings
import os
import healpy as hp
import numpy as np
import astropy.units as u
import matplotlib.pyplot as plt
from .plottools import *

# Fix for macos openMP duplicate bug
os.environ["KMP_DUPLICATE_LIB_OK"] = "True"

def plot(
    input,
    sig=0,
    comp=None,
    freq=None,
    ticks=None,
    min=None,
    max=None,
    cbar=True,
    unit=None,
    coord=None,
    graticule=False,
    projection_type="mollweide",
    fwhm=0.0,
    nside=None,
    mask=None,
    cmap=None,
    norm=None,
    remove_dip=False,
    remove_mono=False,
    title=None,
    ltitle=None,
    width="m",
    darkmode=False,
    ):
    """
    General plotting function for maps.
    This function is a wrapper on healpys projview function with some added features.
    Added features include lognorm, 

    Parameters
    ----------
    input : ndarray, fits file path or cosmoglobe model object
        Map data input given as numpy array either 1d or index given by "sig".
        Also supports fits-file path string or cosmoglobe model.
        If cosmoglobe object is passed such as "model", specify comp or freq.
    sig : list of int or string ["I", "Q", "U"]
        Signal indices to be plotted. 0, 1, 2 interprated as IQU.
        default = [0,]
    comp : string
        Component label for automatic identification of plotting
        parameters based on information from autoparams.json default = None
    freq : float
        frequency in GHz needed for scaling maps when using a model object input
    ticks : list or str
        Min and max value for data. If None, uses 97.5th percentile.
        default = None
    cbar : bool
        Adds a cbar, and "cb" to output filename.
        cbar = False
    graticule : cbar
        Adds graticule to figure.
        default = False
    fwhm : float
        Optional map smoothing. FWHM of gaussian smoothing in arcmin.
        default = 0.0
    mask : array of healpix mask
        Apply a mask file to data
        default = None
    remove_dip : bool
        If mdmask is specified, fits and removes a dipole.
        default = True
    remove_mono : bool
        If mdmask is specified, fits and removes a monopole.
        default = True
    norm : str
        if norm=="linear":
            normal 
        if norm=="log":
            Normalizes data using a semi-logscale linear between -1 and 1.
            Autodetector uses this sometimes, you will be warned.
        default = None
    darkmode : bool
        Plots all outlines in white for dark backgrounds, and adds "dark" in
        filename.
        default = False
    cmap : str
        Colormap (ex. sunburst, planck, jet). Both matplotliib and cmasher
        available as of now. Also supports qualitative plotly map, [ex.
        q-Plotly-4 (q for qualitative 4 for max color)] Sets planck as default.
        default = None
    title : str
        Sets the upper right title. Has LaTeX functionaliity (ex. $A_{s}$.)
        default = None
    ltitle : str
        Sets the upper left title. Has LaTeX functionaliity (ex. $A_{s}$.)
        default = None
    """
    # Pick sizes from size dictionary for page width plots
    if isinstance(width, str):
        width = {
            "x": 2.75,
            "s": 3.5,
            "m": 4.7,
            "l": 7,
        }[width]
    height = width/2
    if cbar:
        height *= 1.275  # Size correction with cbar
    figratio=height/width
    set_style(darkmode)

 
    # Currently not working with projview
    """
    # Make figure
    fig, ax = make_fig(
        (width, height),
        fignum,
        hold,
        subplot,
        reuse_axes, 
        projection="mollweide",
    )
    """

    # Translate sig to correct format
    stokes = ["I", "Q", "U",]
    if isinstance(sig, str):
        sig = stokes.index(sig)

    # Fetching autoset parameters
    params = autoparams(comp, sig, title, ltitle, unit, ticks, min, max, norm, cmap)
    # Parsing component string
    if comp is not None: comp, *specparam = comp.split()

    # If map is string, interprate as file path
    if isinstance(input, str): 
        m = hp.read_map(input, field=sig)
    elif isinstance(input, Model):
        """
        Get data from model object with frequency scaling        
        """
        if comp==None:
            if freq is not None:
                m=input(freq*u.GHz, fwhm=fwhm*u.arcmin,)
            else:
                raise ModelError(
                    f'Model object passed with comp and freq set to None'
                    f'comp: {comp} freq: {freq}'
                )
        else:
            if len(specparam)>0 and isinstance(specparam[0], str):
                m=getattr(input, comp).spectral_parameters[specparam[0]]

                if len(m[sig])==1:
                    warnings.warn("Same value across the whole sky, mapping to array of length Npix")
                    m = np.full(hp.nside2npix(input.nside), m[sig])
            else:
                if freq is not None:
                    m=getattr(input, comp)(freq*u.GHz, fwhm=fwhm*u.arcmin,)
                else:
                    m=getattr(input,comp).amp
        if isinstance(m, u.Quantity):
            m = m.value
    else:
        if isinstance(input, np.ndarray):
            m = input
        else:
            raise TypeError(
                f'Type {type(input)} of input not supported'
                f'Supports numpy array, cosmoglobe model object or fits file string'
            )

    # Make sure we have 1d array at this point
    m = m[sig] if m.ndim > 1 else m

    # Mask map
    if mask is not None:
        m = hp.ma(m)
        m.mask = np.logical_not(mask)

    # udgrade map
    if nside != None and nside != hp.get_nside(m):
        m = hp.ud_grade(m, nside)
    else:
        nside = hp.get_nside(m)

    # Smooth map
    if fwhm > 0.0:
        m = hp.smoothing(m, fwhm)

    print(f"Plotting {comp}, title {title}, nside {nside}")
    
    # Remove mono/dipole
    if remove_dip:
        m = hp.remove_dipole(m, gal_cut=30, copy=True, verbose=True)
    if remove_mono:
        m = hp.remove_monopole(m, gal_cut=30, copy=True, verbose=True)

    # Ticks and ticklabels
    ticks = params["ticks"]
    if ticks == None:
        ticks = get_percentile(m, 97.5)

    #### Logscale ####
    ticklabels = [fmt(i, 1) for i in ticks]
    if params["norm"]=="log":
        m, ticks = apply_logscale(m, ticks, linthresh=1)

    #### Color map #####
    cmap = load_cmap(params["cmap"], params["norm"])

    # Math text in labels
    for i in ["title", "unit", "left_title"]:
        if params[i] and params[i] != "":
            params[i] = r"$" + params[i] + "$"

    # Plot figure
    ret = hp.newvisufunc.projview(m, 
            min=ticks[0], 
            max=ticks[-1],
            cbar=False,
            cmap=cmap,
            projection_type=projection_type,
            graticule=graticule,
            override_plot_properties={"figure_width": width,"figure_size_ratio": figratio,},
            coord=coord,
            )
    
    # Remove color bar because of healpy bug
    plt.gca().collections[-1].colorbar.remove()
    # Add pretty color bar
    if cbar:
        apply_colorbar(
            plt.gcf(), plt.gca(), ret, ticks, ticklabels, params["unit"], linthresh=1, norm=params["norm"])

    #### Right Title ####
    plt.text(4.5, 1.1, params["title"], ha="center", va="center",)
    #### Left Title (stokes parameter label by default) ####
    plt.text(-4.5, 1.1, params["left_title"], ha="center", va="center",)

    
def apply_colorbar(fig, ax, image, ticks, ticklabels, unit, linthresh, norm=None):
    """
    This function applies a colorbar to the figure and formats the ticks.
    """
    from matplotlib.ticker import FuncFormatter

    cb = fig.colorbar(
        image,
        ax=ax,
        orientation="horizontal",
        shrink=0.4,
        pad=0.04,
        ticks=ticks,
        format=FuncFormatter(fmt),
    )
    cb.ax.set_xticklabels(ticklabels)
    cb.ax.xaxis.set_label_text(unit)
    if norm=="log":
        linticks = np.linspace(-1, 1, 3) * linthresh
        logmin = np.round(ticks[0])
        logmax = np.round(ticks[-1])

        logticks_min = -(10 ** np.arange(0, abs(logmin) + 1))
        logticks_max = 10 ** np.arange(0, logmax + 1)
        ticks_ = np.unique(np.concatenate((logticks_min, linticks, logticks_max)))
        # cb.set_ticks(np.concatenate((ticks,symlog(ticks_))), []) # Set major ticks

        logticks = symlog(ticks_, linthresh)
        logticks = [x for x in logticks if x not in ticks]
        cb.set_ticks(np.concatenate((ticks, logticks)))  # Set major ticks
        cb.ax.set_xticklabels(ticklabels + [""] * len(logticks))

        minorticks = np.linspace(-linthresh, linthresh, 5)
        minorticks2 = np.arange(2, 10) * linthresh

        for i in range(len(logticks_min)):
            minorticks = np.concatenate((-(10 ** i) * minorticks2, minorticks))
        for i in range(len(logticks_max)):
            minorticks = np.concatenate((minorticks, 10 ** i * minorticks2))

        minorticks = symlog(minorticks, linthresh)
        minorticks = minorticks[(minorticks >= ticks[0]) & (minorticks <= ticks[-1])]
        cb.ax.xaxis.set_ticks(minorticks, minor=True)

    cb.ax.tick_params(
        which="both",
        axis="x",
        direction="in",
    )
    cb.ax.xaxis.labelpad = 0
    # workaround for issue with viewers, see colorbar docstring
    cb.solids.set_edgecolor("face")
    return cb
