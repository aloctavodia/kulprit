"""Submodel factory class."""

from abc import ABC, abstractmethod
from copy import copy

from typing import Optional, List
from pymc3 import Model

import arviz as az
from arviz import InferenceData
from arviz.utils import one_de

import numpy as np
import torch

from . import ModelData, ModelStructure


class SubModel(ABC):
    """Abstract base class for submodel data classes."""

    @abstractmethod
    def create(self):
        pass


class SubModelStructure(SubModel):
    def __init__(self, ref_model: ModelData) -> None:
        """Submodel object used to create submodels from a reference model.

        Args:
            ref_model (kulprit.data.ModelData): The reference model from which
                to build the submodel
        """

        # log reference model ModelData
        self.ref_model = ref_model

    def generate(self, var_names: List[str]) -> ModelStructure:
        """Generate new ModelStructure class attributes for a submodel.

        Args:
            var_names (list): The names of the parameters to use in the r
                estricted model

        Returns:
            Tuple: Structure attributes of the resulting submodel
        """

        if len(var_names) > 0:
            # extract the submatrix from the reference model's design matrix
            X_res = torch.from_numpy(
                np.column_stack(
                    [self.ref_model.structure.design.common[term] for term in var_names]
                )
            ).float()
            # manually add intercept to new design matrix
            X_res = torch.hstack(
                (torch.ones(self.ref_model.structure.num_obs, 1), X_res)
            )
        else:
            # intercept-only model
            X_res = torch.ones(self.ref_model.structure.num_obs, 1).float()

        # update common term names and dimensions and build new ModelData object
        _, num_terms = X_res.shape
        submode_term_names = ["Intercept"] + var_names
        model_size = len(var_names)

        return X_res, num_terms, model_size, submode_term_names, var_names

    def create(self, var_names: List[str]) -> ModelStructure:
        """Build a submodel from a reference model containing specific terms.

        Args:
            var_names (list): The names of the parameters to use in the r
                estricted model

        Returns:
            ModelData: The resulting submodel `ModelData` object
        """

        # copy and instantiate new ModelStructure object
        sub_model_structure = copy(self.ref_model.structure)
        (
            sub_model_structure.X,
            sub_model_structure.num_terms,
            sub_model_structure.model_size,
            sub_model_structure.term_names,
            sub_model_structure.common_terms,
        ) = self.generate(var_names)

        # ensure correct dimensions
        assert sub_model_structure.X.shape == (
            self.ref_model.structure.num_obs,
            sub_model_structure.model_size + 1,
        )
        return sub_model_structure


class SubModelInferenceData(SubModel):
    def __init__(self, ref_model: ModelData) -> None:
        """Submodel object used to create submodels from a reference model.

        Args:
            ref_model (kulprit.data.ModelData): The reference model from which
                to build the submodel
        """

        # log reference model ModelData
        self.ref_model = ref_model

    def create(
        self,
        sub_model_structure: SubModelStructure,
        theta_perp: torch.tensor,
        disp_perp: Optional[torch.tensor] = None,
    ) -> InferenceData:
        """Convert some set of pytorch tensors into an ArviZ idata object.

        Args:
            model (kulprit.ModelData): The restricted ModelData object whose
                posterior to build
            theta_perp (torch.tensor): Restricted parameter posterior projections,
                including the intercept term
            disp_perp (torch.tensor): Restricted model dispersions parameter
                posterior projections

        Returns:
            arviz.inferencedata: Restricted model idata object
        """

        # reshape `theta_perp` so it has the same shape as the reference model
        num_chain = len(self.ref_model.idata.posterior.coords.get("chain"))
        num_draw = len(self.ref_model.idata.posterior.coords.get("draw"))
        num_terms = sub_model_structure.num_terms
        num_obs = self.ref_model.structure.num_obs

        theta_perp = torch.reshape(theta_perp, (num_chain, num_draw, num_terms))

        # build posterior dictionary from projected parameters
        posterior = {
            term: theta_perp[:, :, i]
            for i, term in enumerate(sub_model_structure.term_names)
        }
        if disp_perp is not None:
            # reshape `disp_perp` if present
            disp_perp = torch.reshape(disp_perp, (num_chain, num_draw))
            # update the posterior draws dictionary with dispersion parameter
            disp_dict = {
                f"{self.ref_model.structure.response_name}_sigma": disp_perp,
                f"{self.ref_model.structure.response_name}_sigma_log__": torch.log(
                    disp_perp
                ),
            }

            # TODO: find a way to automatically perform the inverse PyMC
            # transformation for transformed dispersion parameters

            posterior.update(disp_dict)

        # build points data from the posterior dictionaries
        points = self.posterior_to_points(posterior)

        # compute log-likelihood of projected model from this posterior
        log_likelihood = self.compute_log_likelihood(
            self.ref_model.structure.backend, points
        )

        # reshape the log-likelihood values to be inline with reference model
        log_likelihood.update(
            (key, value.reshape(num_chain, num_draw, num_obs))
            for key, value in log_likelihood.items()
        )

        # add observed data component of projected idata
        observed_data = {
            self.ref_model.structure.response_name: self.ref_model.idata.observed_data.get(
                "y"
            )
            .to_dict()
            .get("data")
        }

        # build idata object for the projected model
        idata = az.data.from_dict(
            posterior=posterior,
            log_likelihood=log_likelihood,
            observed_data=observed_data,
        )
        return idata

    def posterior_to_points(self, posterior: dict) -> list:
        """Convert the posterior samples from a restricted model into list of dicts.

        This list of dicts datatype is referred to a `points` in PyMC, and is needed
        to be able to compute the log-likelihood of a projected model, here
        `res_model`.

        Args:
            posterior (dict): Dictionary of posterior restricted model samples

        Returns:
            list: The list of dictionaries of point samples
        """

        # build samples dictionary from posterior of idata
        samples = {
            key: (
                posterior[key].flatten()
                if key in posterior.keys()
                else np.zeros((self.ref_model.structure.num_draws,))
            )
            for key in self.ref_model.structure.backend.model.test_point.keys()
        }
        # extract observed and unobserved RV names and sample matrix
        var_names = list(samples.keys())
        obs_matrix = np.vstack(list(samples.values()))
        # build points list of dictionaries
        points = [
            {
                var_names[j]: (
                    np.array([obs_matrix[j, i]])
                    if var_names[j]
                    != f"{self.ref_model.structure.response_name}_sigma_log__"
                    else np.array(obs_matrix[j, i])
                )
                for j in range(obs_matrix.shape[0])
            }
            for i in range(obs_matrix.shape[1])
        ]
        return points

    def compute_log_likelihood(self, backend: Model, points: list) -> dict:
        """Compute log-likelihood of some data points given a PyMC model.

        Args:
            backend (pymc.Model) : PyMC3 model for which to compute log-likelihood
            points (list) : List of dictionaries, where each dictionary is a named
                sample of all parameters in the model

        Returns:
            dict: Dictionary of log-liklelihoods at each point
        """

        cached = [(var, var.logp_elemwise) for var in backend.model.observed_RVs]

        log_likelihood_dict = {}
        for var, log_like_fun in cached:
            log_likelihood = np.array([one_de(log_like_fun(point)) for point in points])
            log_likelihood_dict[var.name] = log_likelihood
        return log_likelihood_dict
