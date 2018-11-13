import numpy as np
from itertools import combinations

from pymatgen import Structure
from pymatgen.core.tensors import Tensor
from pymatgen.analysis.piezo import PiezoTensor
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from maggma.builders import MapBuilder

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class DielectricBuilder(MapBuilder):
    def __init__(self, materials, dielectric, query=None, **kwargs):
        """
        Creates a dielectric collection for materials

        Args:
            materials (Store): Store of materials documents to match to
            dielectric (Store): Store of dielectric properties
            min_band_gap (float): minimum band gap for a material to look for a dielectric calculation to build
            query (dict): dictionary to limit materials to be analyzed
        """

        self.materials = materials
        self.dielectric = dielectric

        self.query = query if query else {}
        self.query.update({"dielectric": {"$exists": 1}, "bandstructure.band_gap": {"$gt": 0.0}})

        super().__init__(
            source=materials,
            target=dielectric,
            query=self.query,
            ufn=self.calc,
            projection=["dielectric", "piezo", "structure"],
            **kwargs)

    def calc(self, item):
        """
        Process the tasks and materials into a dielectrics collection

        Args:
            item dict: a dict of material_id, structure, and tasks

        Returns:
            dict: a dieletrics dictionary
        """

        def poly(matrix):
            diags = np.diagonal(matrix)
            return np.prod(diags) / np.sum(np.prod(comb) for comb in combinations(diags, 2))

        structure = Structure.from_dict(item.get("dielectric", {}).get("structure", None))

        ionic = Tensor(item["dielectric"]["ionic"]).symmetrized.fit_to_structure(structure).convert_to_ieee(structure)
        static = Tensor(item["dielectric"]["static"]).symmetrized.fit_to_structure(structure).convert_to_ieee(structure)
        total = ionic + static

        d = {
            "dielectric": {
                "total": total,
                "ionic": ionic,
                "static": static,
                "e_total": np.average(np.diagonal(total)),
                "e_ionic": np.average(np.diagonal(ionic)),
                "e_static": np.average(np.diagonal(static)),
                "n": np.sqrt(np.average(np.diagonal(static))),
            }
        }

        sga = SpacegroupAnalyzer(structure)
        # Update piezo if non_centrosymmetric
        if item.get("piezo", False) and not sga.is_laue():
            static = PiezoTensor.from_voigt(np.array(
                item['piezo']["static"])).fit_to_structure(structure).convert_to_ieee(structure).voigt
            ionic = PiezoTensor.from_voigt(np.array(
                item['piezo']["ionic"])).fit_to_structure(structure).convert_to_ieee(structure).voigt
            total = ionic + static

            directions, charges, strains = np.linalg.svd(total)

            max_index = np.argmax(np.abs(charges))
            d["piezo"] = {
                "total": total,
                "ionic": ionic,
                "static": static,
                "e_ij_max": charges[max_index],
                "max_direction": directions[max_index],
                "strain_for_max": strains[max_index]
            }

        return d
