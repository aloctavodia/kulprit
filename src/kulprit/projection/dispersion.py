"""Dispersion parameter projection class."""

from abc import ABC, abstractmethod

from ..data import ModelData

import torch
import numpy as np


class DispersionProjector(ABC):
    """Base dispersion parameter projector class."""

    @abstractmethod
    def forward(self):
        pass


class GaussianDispersionProjector(DispersionProjector):
    """Gaussian model dispersion parameter projector."""

    def __init__(self, ref_model: ModelData) -> None:
        self.ref_model = ref_model

    def solve(
        self, theta_ast: torch.tensor, theta_perp: torch.tensor, sigma_ast: torch.tensor
    ) -> np.ndarray:
        """Analytic solution to the dispersion parameter projection.

        We separate this solution from the `foward` method to allow for
        vectorisation of the projection across samples.

        Args:
            theta_ast (torch.tensor):
            theta_perp (torch.tensor):
            sigma_ast (torch.tensor):

        Returns:
            np.ndarray: The sample projection of the dispersion parameter in a
                Gaussian model according to the analytic solution
        """

        f = self.X_ast @ theta_ast
        f_perp = self.X_perp @ theta_perp
        sigma_perp = torch.sqrt(
            sigma_ast**2
            + 1 / self.ref_model.structure.num_obs * (f - f_perp).T @ (f - f_perp)
        )
        sigma_perp = sigma_perp.numpy()
        return sigma_perp

    def forward(self, theta_perp: torch.tensor, X_perp: torch.tensor):
        """Analytic projection of the model dispersion parameters.

        Args:
            theta_perp (torch.tensor): A PyTorch tensor of the restricted
                parameter draws
            X_perp (np.ndarray): The design matrix of the restricted model we
                are projecting onto

        Returns:
            torch.tensor: The restricted projections of the dispersion parameters
        """

        # log the submodel design matrix
        self.X_perp = X_perp

        # extract parameter draws from both models
        theta_ast = torch.from_numpy(
            self.ref_model.idata.posterior.stack(samples=("chain", "draw"))[
                self.ref_model.structure.term_names
            ]
            .to_array()
            .transpose(*("samples", "variable"))
            .values
        ).float()
        sigma_ast = torch.from_numpy(
            self.ref_model.idata.posterior.stack(samples=("chain", "draw"))[
                self.ref_model.structure.response_name + "_sigma"
            ]
            .transpose()
            .values
        ).float()
        self.X_ast = self.ref_model.structure.X

        # project the dispersion parameter
        vec_solve = np.vectorize(
            self.solve, signature="(n),(m),()->()", doc="Vectorised `_proj` method"
        )
        sigma_perp = (
            torch.from_numpy(vec_solve(theta_ast, theta_perp, sigma_ast))
            .flatten()
            .float()
        )

        # assure correct shape
        assert sigma_perp.shape == sigma_ast.shape
        return sigma_perp


class DispersionProjectorFactory:
    """Factory class for the dispersion parameter projectors."""

    def __init__(self, ref_model: ModelData) -> None:
        """Dispersion parameter projection module constructor.

        Args:
            ref_model (ModelData): The reference model object whose dispersion
                parameters we wish to project
        """

        # log family name and reference model
        self.family = ref_model.structure.family
        self.ref_model = ref_model

        # define all available KL divergence loss classes
        self.family_dict = {
            "gaussian": GaussianDispersionProjector,
        }

        if self.family not in self.family_dict:
            raise NotImplementedError(
                f"The {self.family} class has not yet been implemented."
            )

    def factory_method(self) -> DispersionProjector:
        """Choose the appropriate divergence class given the model."""

        # fetch appropriate divergence class given model variate family
        disp_projector = self.family_dict[self.family]
        return disp_projector(self.ref_model)

    def forward(self, theta_perp: torch.tensor, X_perp: torch.tensor) -> torch.tensor:
        """Project dispersion parameters of the submodel.

        Args:
            theta_perp (torch.tensor): A PyTorch tensor of the restricted
                parameter draws
            X_perp (np.ndarray): The design matrix of the restricted model we
                are projecting onto

        Returns:
            torch.tensor: The projections of the submodel's dispersion parameters
        """

        projection_method = self.factory_method()
        disp_params = projection_method.forward(theta_perp, X_perp)
        return disp_params
