import astropy.constants as const
import astropy.units as u
from numba import njit
import numpy as np

from .skycomponent import SkyComponent

h = const.h.value
c = const.c.value
k_B = const.k_B.value


class Dust(SkyComponent):
    """
    Parent class for all Dust models.
    
    """
    comp_label = 'dust'

    def __init__(self, data, **kwargs):
        super().__init__(data, **kwargs)
        self.kwargs = kwargs


class ModifiedBlackbody(Dust):
    """
    Model for modifed blackbody emission from thermal dust.
    
    """
    model_label = 'MBB'

    def __init__(self, data, nside=None, fwhm=None):
        super().__init__(data, nside=nside, fwhm=fwhm)


    @u.quantity_input(nu=u.Hz)
    def get_emission(self, nu):
        """
        Returns the model emission at an arbitrary frequency nu in units 
        of K_RJ.

        Parameters
        ----------
        nu : astropy.units.quantity.Quantity
            Frequencies at which to evaluate the model. 

        Returns
        -------
        emission : astropy.units.quantity.Quantity
            Model emission at given frequency in units of K_RJ.

        """
        scaling = self._get_freq_scaling(nu.si.value, 
                                         self.params['nu_ref'].si.value, 
                                         self.beta, 
                                         self.T.value)
        emission =  self.amp*scaling

        return emission


    @staticmethod
    @njit
    def _get_freq_scaling(nu, nu_ref, beta, T):
        """
        Computes the frequency scaling from the reference frequency nu_ref to 
        an arbitrary frequency nu, which depends on the spectral parameters
        beta and T.

        Parameters
        ----------
        nu : int, float, numpy.ndarray
            Frequencies at which to evaluate the model. 
        nu_ref : int, float, numpy.ndarray
            Reference frequency.        
        beta : numpy.ndarray
            Dust beta map.
        T : numpy.ndarray
            Dust temperature map.

        Returns
        -------
        scaling : numpy.ndarray
            Frequency scaling factor.

        """
        nu_ref = np.expand_dims(nu_ref, axis=1)

        scaling = (nu/nu_ref)**(beta-2)
        scaling *= blackbody_emission(nu, T) / blackbody_emission(nu_ref, T)

        return scaling



@njit
def blackbody_emission(nu, T):
    """
    Returns the emission emitted by a blackbody with with temperature T at 
    a frequency nu.

    Parameters
    ----------
    nu : int, float, numpy.ndarray
        Frequency at which to evaluate the blackbody radiation.
    T : numpy.ndarray
        Temperature of the blackbody. 

    Returns
    -------
    numpy.ndarray
        Blackbody emission in units of Jy/sr

    """
    return ((2*h*nu**3)/c**2) / np.expm1(h*nu/(k_B*T))
