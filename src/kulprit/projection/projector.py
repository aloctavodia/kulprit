"""Base projection class."""

from fastcore.dispatch import typedispatch
from typing import Optional, List, Union
from typing_extensions import Literal

from kulprit.data.data import ModelData
from kulprit.data.submodel import SubModelStructure, SubModelInferenceData
from kulprit.families.family import Family
from kulprit.projection.solvers.solver import Solver


class Projector:
    def __init__(
        self,
        data: ModelData,
        num_iters: Optional[int] = 200,
        learning_rate: Optional[float] = 0.01,
    ) -> None:
        """Reference model builder for projection predictive model selection.

        This class handles the core projection methods of the model selection
        procedure. Note that throughout the procedure, variables with names of
        the form ``*_ast`` belong to the reference model while variables with
        names like ``*_perp`` belong to the restricted model. This is to
        preserve notation choices from previous papers on the topic.

        Args:
            data (kulprit.data.ModelData): Reference model dataclass object
            num_iters (int): Number of iterations over which to run backprop
            learning_rate (float): The backprop optimiser's learning rate
        """

        # log reference model data object
        self.data = data

        # build model family
        self.family = Family(self.data)

        # set optimiser parameters
        self.num_iters = num_iters
        self.learning_rate = learning_rate

    def project(
        self,
        terms: Union[List[str], int],
        method: Literal["analytic", "gradient"],
    ) -> ModelData:
        """Wrapper function for projection method.

        Args:
            terms (Union[List[str], int]): Either a list of strings containing
                the names of the parameters to include the submodel, or the
                number of parameters to include in the submodel, **not**
                including the intercept term
            method (str): The projection method to employ, either "analytic" to
                use the hard-coded solutions the optimisation problem, or
                "gradient" to employ gradient descent methods

        Returns:
            kulprit.data.ModelData: Projected submodel ``ModelData`` object
        """

        # project terms by name
        if isinstance(terms, list):
            # test `terms` input
            if not all([term in self.data.structure.term_names for term in terms]):
                raise UserWarning(
                    "Please ensure that all terms selected for projection exist in"
                    + " the reference model."
                )

            # perform projection
            return self.project_names(term_names=terms, method=method)

        # project a number of terms
        elif isinstance(terms, int):
            # in the future we will select the "best" `args` variables according to a
            # previously run search
            raise NotImplementedError(
                "The project method currently only accepts the names of the "
                + "parameters to project as inputs",
            )

        else:
            raise UserWarning(
                "Please provide either the number of parameters to project "
                + "onto the submodel, or their names as a list of strings."
            )

    def project_names(
        self,
        term_names: List[List[str]],
        method: Literal["analytic", "gradient"],
    ) -> ModelData:
        """Primary projection method for GLM reference model.

        The projection is defined as the values of the submodel parameters
        minimising the Kullback-Leibler divergence between the submodel
        and the reference model. This is perform numerically using PyTorch and
        Adam for the optimisation.

        Args:
            term_names (List[str]): The names of parameters to project onto the
                submodel, **not** including the intercept term
            method (str): The method to use in projection

        Returns:
            kulprit.data.ModelData: Projected submodel ``ModelData`` object
        """

        # build restricted model object
        structure_factory = SubModelStructure(self.data)
        submodel_structure = structure_factory.create(term_names)

        # build solver
        self.solver = Solver(
            data=self.data,
            family=self.family,
            method=method,
            num_iters=self.num_iters,
            learning_rate=self.learning_rate,
        )

        # solve the parameter projections depending on method
        theta_perp, final_loss = self.solver.solve(submodel_structure)

        # extract restricted design matrix
        X_perp = submodel_structure.X

        # project dispersion parameters in the model, if present
        disp_perp = self.solver.solve_dispersion(theta_perp, X_perp)

        # build the complete restricted model posterior
        idata_factory = SubModelInferenceData(self.data)
        sub_model_idata = idata_factory.create(submodel_structure, theta_perp, disp_perp)

        # finally, combine these projected structure and idata into `ModelData`
        sub_model = ModelData(
            structure=submodel_structure,
            idata=sub_model_idata,
            dist_to_ref_model=final_loss,
        )
        return sub_model
