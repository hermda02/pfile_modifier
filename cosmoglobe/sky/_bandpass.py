from typing import Dict, List, Protocol, Union

from astropy.units import Quantity, Unit
import numpy as np
from scipy.interpolate import RectBivariateSpline

from cosmoglobe.sky._intensity_derivative import get_intensity_derivative

# key: interpolation dimensions, value: number of points in the interpolate
N_INTERPOLATION_GRID = {1: 1000, 2: 100}


def get_normalized_bandpass(freqs: Quantity, bandpass: Quantity) -> Quantity:
    """Normalizes a bandpass to units of unity under integration.

    Parameters
    ----------
    freqs
        Frequencies corresponding to bandpass weights.
    bandpass
        The bandpass profile.

    Returns
    -------
        Bandpass with unit integral over np.trapz.
    """

    return bandpass / np.trapz(bandpass, freqs)


def get_bandpass_coefficient(
    freqs: Quantity,
    bandpass: Quantity,
    input_unit: Unit,
    output_unit: Unit,
) -> Quantity:
    """Returns the bandpass coefficient.

    Parameters
    ----------
    freqs
        Frequencies corresponding to bandpass weights.
    bandpass
        The bandpass profile.
    input_unit
        The unit of the cosmoglobe data.
    ouput_unit
        The requested output unit of the simulated emission

    Returns
    -------
    coefficient
        Bandpass coefficient representing the unitconversion between the
        input/ouput unit over the bandpass.
    """

    in_intensity_derivative = get_intensity_derivative(input_unit)
    out_intensity_derivative = get_intensity_derivative(output_unit)
    coefficient = np.trapz(bandpass * in_intensity_derivative(freqs), freqs) / np.trapz(
        bandpass * out_intensity_derivative(freqs), freqs
    )

    return coefficient


class FreqScalingFunction(Protocol):
    """Interface for a function that returns the frequency scaling of a sky component."""

    def __call__(self, freqs: Quantity, **spectral_parameters: Quantity) -> Quantity:
        """Signature matching the `get_freq_scaling` functions signature."""


class BandpassIntegration(Protocol):
    """Interface for a bandpass integration implementation."""

    def __call__(
        self,
        freqs: Quantity,
        bandpass: Quantity,
        freq_scaling_func: FreqScalingFunction,
        spectral_parameters: Dict[str, Quantity],
        interpolation_grid: Dict[str, Union[np.ndarray, Quantity]],
    ) -> Union[float, List[float]]:
        """Computes the frequency scaling factor over bandpass integration.

        The bandpass integration is performed using the Commander mixing matrix
        formalism. Rather than computing the frequency scaling factor per pixel
        for each frequency in the bandpass, we grid out the spectral parameters
        of the component to a small range covering the spatial variations over 
        IQU. We then compute the frequency scaling factor for each gridded 
        parameter integrated over the bandpass and store these values. To 
        estimate the bandpass integration factor, we then simply interpolate in 
        these values.

        Parameters
        ----------
        freqs
            Frequencies corresponding to bandpass weights.
        bandpass
            The bandpass profile.
        freq_scaling_func
            Function that returns the SED scaling given frequencies and 
            spectral parameters.
        spectral_parameters
            Dictionary containing the spectral parameters of the component we
            want to integrate over a bandpass.
        interpolation_grid
            Grid of spectral parameter values for the component. This grid
            used as interpolation values to compute the interpolated scaling
            factor.

        Returns
        -------
            Bandpass integration factor.
        """


class BandpassIntegration0D:
    """Interpolation algorithm for a component with no spatially varying spectral parameters."""

    def __call__(
        self,
        freqs: Quantity,
        bandpass: Quantity,
        freq_scaling_func: FreqScalingFunction,
        spectral_parameters: Dict[str, Quantity],
        *_,
    ) -> float:

        freq_scaling = freq_scaling_func(freqs, **spectral_parameters)
        bandpass_scaling_factor = np.trapz(freq_scaling * bandpass, freqs)
        if np.ndim(bandpass_scaling_factor) > 0:
            return np.expand_dims(bandpass_scaling_factor, axis=1)

        return bandpass_scaling_factor


class BandpassIntegration1D:
    """Interpolation algorithm for a component with a single spatially varying spectral parameter."""

    def __call__(
        self,
        freqs: Quantity,
        bandpass: Quantity,
        freq_scaling_func: FreqScalingFunction,
        spectral_parameters: Dict[str, Quantity],
        interpolation_grid: Dict[str, Union[np.ndarray, Quantity]],
    ) -> List[float]:

        # Grid dictionary only has one item
        ((key, spectral_parameter_grid),) = interpolation_grid.items()
        if spectral_parameters[key].shape[0] == 3:
            integrals = np.zeros((len(spectral_parameter_grid), 3))
        else:
            integrals = np.zeros((len(spectral_parameter_grid), 1))

        for idx, grid_point in enumerate(spectral_parameter_grid):
            scalar_params = {
                param: value
                for param, value in spectral_parameters.items()
                if param != key
            }
            freq_scaling = freq_scaling_func(
                freqs, **{key: grid_point}, **scalar_params
            )
            integrals[idx] = np.trapz(freq_scaling * bandpass, freqs)

        # We transpose the array to make it into row format similar to how
        # regular IQU maps are stored
        integrals = np.transpose(integrals)

        scaling = [
            np.interp(
                spectral_parameters[key][idx].value,
                spectral_parameter_grid.value,
                col,
            )
            for idx, col in enumerate(integrals)
        ]

        return scaling


class BandpassIntegration2D:
    """Interpolation algorithm for a component with two spatially varying spectral parameters."""

    def __call__(
        self,
        freqs: Quantity,
        bandpass: Quantity,
        freq_scaling_func: FreqScalingFunction,
        spectral_parameters: Dict[str, Quantity],
        interpolation_grid: Dict[str, Union[np.ndarray, Quantity]],
    ) -> List[float]:

        mesh_grid = {
            key: value
            for key, value in zip(
                interpolation_grid.keys(), np.meshgrid(*interpolation_grid.values())
            )
        }

        # Make n x n mesh grid for the spectral parameters
        n = len(list(interpolation_grid.values())[0])
        if any(
            spectral_param.shape[0] == 3
            for spectral_param in spectral_parameters.values()
        ):
            integrals = np.zeros((n, n, 3))
        else:
            integrals = np.zeros((n, n, 1))

        for i in range(n):
            for j in range(n):
                grid_spectrals = {key: value[i, j] for key, value in mesh_grid.items()}
                freq_scaling = freq_scaling_func(freqs, **grid_spectrals)
                integrals[i, j] = np.trapz(freq_scaling * bandpass, freqs)
        integrals = np.transpose(integrals)

        scaling = []
        for idx, col in enumerate(integrals):
            f = RectBivariateSpline(*interpolation_grid.values(), col)
            packed_spectrals = [
                spectral[idx] if spectral.shape[0] == 3 else spectral[0]
                for spectral in spectral_parameters.values()
            ]
            scaling.append(f(*packed_spectrals, grid=False))

        return scaling


BANDPASS_INTEGRATION_IMPLEMENTATIONS: Dict[int, BandpassIntegration] = {
    0: BandpassIntegration0D(),
    1: BandpassIntegration1D(),
    2: BandpassIntegration2D(),
}


def get_interpolation_grid(
    spectral_parameters: Dict[str, Quantity]
) -> Dict[str, Union[np.ndarray, Quantity]]:
    """Returns a interpolation range.

    Computes the interpolation range of the spectral parameters of a
    sky component. We use a regular grid with n points for the range.

    Parameters
    ----------
    spectral_parameters
        Dictionary containing the spectral parameters of a given component.

    Returns
    -------
    interp_parameters
        Dictionary with a interpolation grid for each spatially varying
        spectral parameter.
    """

    dim = 0
    for spectral_parameter in spectral_parameters.values():
        if spectral_parameter.size > 3:
            dim += 1

    grid: Dict[str, Union[np.ndarray, Quantity]] = {}
    if dim == 0:
        return grid

    try:
        n = N_INTERPOLATION_GRID[dim]
    except KeyError:
        raise NotImplementedError(
            "Bandpass integration for comps with more than two spectral "
            "parameters is not currently supported"
        )
    for key, value in spectral_parameters.items():
        if value.size > 3:
            grid_range = np.linspace(np.amin(value), np.amax(value), n)
            grid[key] = grid_range

    return grid


def get_bandpass_scaling(
    freqs: Quantity,
    bandpass: Quantity,
    freq_scaling_func: FreqScalingFunction,
    spectral_parameters: Dict[str, Quantity],
) -> Union[float, List[float]]:
    """Returns the appropriate Bandpass integration implementation given the spectral parameters."""

    grid = get_interpolation_grid(spectral_parameters)
    dim = len(grid)

    if dim not in BANDPASS_INTEGRATION_IMPLEMENTATIONS:
        raise NotImplementedError(
            "Bandpass integration for comps with more than two spectral "
            "parameters is not currently supported"
        )

    return BANDPASS_INTEGRATION_IMPLEMENTATIONS[dim](
        freqs, bandpass, freq_scaling_func, spectral_parameters, grid
    )
