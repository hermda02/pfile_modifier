from dataclasses import dataclass
import inspect
from typing import Union, Optional, Literal

import astropy.units as u
import healpy as hp
from tqdm import tqdm

from cosmoglobe.h5.chain import Chain, ChainVersion
from cosmoglobe.h5.context import chain_context
from cosmoglobe.h5.exceptions import (
    ChainComponentNotFoundError,
    ChainKeyError,
    ChainFormatError,
)
from cosmoglobe.sky.model import Model
from cosmoglobe.sky.base import SkyComponent
from cosmoglobe.sky import COSMOGLOBE_COMPS


DEFAULT_SAMPLE = -1


@dataclass
class ModelFactory:
    """Class that creates sky models from chains."""

    chain: Chain
    samples: Optional[Union[range, int]] = None
    burn_in: Optional[int] = None

    def create(self, nside: Optional[int] = None) -> Model:
        """Initialize and return a sky component from a chainfile."""

        if self.chain.version is ChainVersion.OLD:
            raise ChainFormatError(
                "cannot initialize a sky model from a chain without a "
                "parameter group"
            )

        model = Model(nside=nside)
        with tqdm(total=len(self.chain.components)) as progress_bar:
            padding = len(max(self.chain.components, key=len))
            for component in self.chain.components:
                progress_bar.set_description(f"{component:<{padding}}")
                initialized_component = self.init_component(component, nside)
                model._add_component_to_model(initialized_component)
                progress_bar.update()

        return model

    def init_component(
        self, component: str, nside: Optional[int] = None
    ) -> SkyComponent:
        """Initialize and return a sky component from a chainfile.

        Parameters
        ----------
        component
            Name of the component in the chain.
        chain
            Chain object.
        nside
            Model HEALPIX map resolution parameter.

        Returns
        -------
            Initialized sky component object.
        """
        try:
            comp_class = COSMOGLOBE_COMPS[component]
        except KeyError:
            raise ChainComponentNotFoundError(
                f"{component=!r} is not part in the Cosmoglobe Sky Model"
            )

        signature = inspect.signature(comp_class)
        class_args = list(signature.parameters.keys())

        args = {}

        # Contexts are operations that needs to be done to the data in the
        # chain before it can be used in the sky model.
        mappings = chain_context.get_mappings(component)
        units = chain_context.get_units(component)
        pre_contexts = chain_context.get_pre_context(component)
        for context in pre_contexts:
            args = context.context(args)

        for arg in class_args:
            chain_arg = mappings.get(arg, arg)
            chain_params = self.chain.parameters[component]

            if chain_arg in chain_params:
                value = chain_params[chain_arg]
            else:
                try:
                    value = self.chain.mean(
                        f"{component}/{chain_arg}_alm", samples=self.samples
                    )
                    is_alm = True
                except ChainKeyError:
                    try:
                        value = self.chain.mean(
                            f"{component}/{chain_arg}", samples=self.samples
                        )
                    except ChainKeyError:
                        value = self.chain.mean(
                            f"{component}/{chain_arg}_map", samples=self.samples
                        )
                    is_alm = False

                if is_alm:
                    pol = True if arg == "amp" and value.shape[0] == 3 else False
                    value = hp.alm2map(
                        value,
                        nside=nside if nside is not None else chain_params["nside"],
                        fwhm=(chain_params["fwhm"] * u.arcmin).to("rad").value,
                        pol=pol,
                    )

            args[arg] = u.Quantity(value, unit=units[arg] if arg in units else None)

        post_contexts = chain_context.get_post_context(component)
        for context in post_contexts:
            args = context.context(args)

        return comp_class(**args)


def model_from_chain(
    chain: Union[str, Chain],
    nside: Optional[int] = None,
    samples: Union[range, int, Literal["all"]] = DEFAULT_SAMPLE,
    burn_in: Optional[int] = None,
) -> Model:
    """Initialize and return a cosmoglobe sky model from a chainfile.

    Parameters
    ----------
    chain
        Path to a Cosmoglobe chainfile or a Chain object.
    nside
        Model HEALPIX map resolution parameter.
    samples
        The sample number for which to extract the model. If the input
        is 'all', then the model will an average of all samples in the chain.
        Defaults to the last sample in the chain.
    burn_in
        Burn in sample in the chain.

    Returns
    -------
    model
        Initialized sky mode object.
    """

    if not isinstance(chain, Chain):
        chain = Chain(chain, burn_in)

    if isinstance(samples, str):
        if samples.lower() == "all":
            samples = range(1, len(chain.samples))
        else:
            raise ValueError("samples must be either 'all', an int, or a range")
        
    model_factory = ModelFactory(chain, samples, burn_in)

    return model_factory.create(nside)
