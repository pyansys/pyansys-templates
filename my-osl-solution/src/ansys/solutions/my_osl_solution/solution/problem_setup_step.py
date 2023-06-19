# ©2023, ANSYS Inc. Unauthorized use, distribution or duplication is prohibited.

"""Backend of the problem setup step."""

import json
from pathlib import Path
import platform
import time

from ansys.optislang.core import Optislang
from ansys.saf.glow.solution import FileGroupReference, FileReference, StepModel, StepSpec, long_running, transaction
from ansys.solutions.optislang.parser.project_properties import (
    ProjectProperties,
    apply_placeholders_to_properties_file,
    write_properties_file,
)
from ansys.solutions.products_ecosystem.controller import AnsysProductsEcosystemController
from ansys.solutions.products_ecosystem.utils import convert_to_long_version

from ansys.solutions.hook_optimization.model.utils import read_system_hierarchy
from ansys.solutions.hook_optimization.ui.utils.monitoring import _get_actor_hids


class ProblemSetupStep(StepModel):
    """Step model of the problem setup step."""

    # Parameters ------------------------------------------------------------------------------------------------------

    # Frontend persistence
    ansys_ecosystem_ready: bool = False
    optislang_solve_status: str = "initial"  # initial, processing, finished, stopped, aborted, idle
    placeholder_values: dict = {}
    placeholder_definitions: dict = {}
    ui_placeholders: dict = {}
    app_metadata: dict = {}
    analysis_running: bool = False

    # Backend data model
    tcp_server_host: str = "127.0.0.1"
    tcp_server_port: int = None
    ansys_ecosystem: dict = {
        "optislang": {
            "authorized_versions": ["2022.2", "2023.1"],
            "installed_versions": [],
            "compatible_versions": [],
            "selected_version": None,
            "alert_message": "OptiSLang install not checked.",
            "alert_color": "warning",
        }
    }
    system_hierarchy: dict = {}
    project_status_info: dict = {}
    actors_info: dict = {}
    actors_status_info: dict = {}
    results_files: dict = {}
    tcp_server_stopped_states = ["idle", "finished", "stopped", "aborted"]

    # File storage ----------------------------------------------------------------------------------------------------

    # Inputs
    project_file: FileReference = FileReference("Problem_Setup/hook_optimization.opf ")
    properties_file: FileReference = FileReference("Problem_Setup/hook_optimization.json ")
    metadata_file: FileReference = FileReference("Problem_Setup/metadata_file.json")
    system_hierarchy_file: FileReference = FileReference("Problem_Setup/system_hierarchy.json")

    # Outputs
    working_properties_file: FileReference = FileReference("Problem_Setup/working_properties_file.json")
    server_info_file: FileReference = FileReference("Problem_Setup/server_info.ini")

    # Methods ---------------------------------------------------------------------------------------------------------

    @transaction(self=StepSpec(download=["properties_file"], upload=["placeholder_values", "placeholder_definitions"]))
    def get_default_placeholder_values(self) -> None:
        """Get placeholder values and definitions using the ProjectProperties class."""
        pp = ProjectProperties()
        pp.read_file(self.properties_file.path)
        placeholders = pp.get_properties()["placeholders"]
        self.placeholder_values = placeholders.get("placeholder_values")
        self.placeholder_definitions = placeholders.get("placeholder_definitions")

    @transaction(self=StepSpec(download=["properties_file", "ui_placeholders"], upload=["working_properties_file"]))
    def write_updated_properties_file(self) -> None:
        properties = apply_placeholders_to_properties_file(self.ui_placeholders, self.properties_file.path)
        write_properties_file(properties, Path(self.working_properties_file.path))

    @transaction(
        self=StepSpec(
            upload=["project_file", "properties_file", "workbench_input_deck", "metadata_file", "system_hierarchy_file"]
        )
    )
    def upload_bulk_files_to_project_directory(self) -> None:
        """Upload bulk files to project directory."""

        original_project_file = Path(__file__).parent.absolute().parent / "model" / "assets" / hook_optimization.opf 
        self.project_file.write_bytes(original_project_file.read_bytes())

        original_properties_file = (
            Path(__file__).parent.absolute().parent / "model" / "assets" / hook_optimization.json 
        )
        self.properties_file.write_bytes(original_properties_file.read_bytes())

        original_metadata_file = Path(__file__).parent.absolute().parent / "model" / "assets" / "metadata.json"
        self.metadata_file.write_bytes(original_metadata_file.read_bytes())

        original_system_hierarchy_file = (
            Path(__file__).parent.absolute().parent / "model" / "assets" / "system_hierarchy.json"
        )
        self.system_hierarchy_file.write_bytes(original_system_hierarchy_file.read_bytes())

    @transaction(self=StepSpec(download=["metadata_file"], upload=["app_metadata"]))
    def get_app_metadata(self) -> None:
        """Read OWA metadata file."""

        with open(self.metadata_file.path) as f:
            self.app_metadata = json.load(f)

    @transaction(
        self=StepSpec(
            upload=["ansys_ecosystem", "ansys_ecosystem_ready"],
        )
    )
    def check_ansys_ecosystem(self) -> None:
        """Check if Ansys Products are installed and if the appropriate versions are available."""

        self.ansys_ecosystem_ready = True

        controller = AnsysProductsEcosystemController()

        for product_name in self.ansys_ecosystem.keys():

            self.ansys_ecosystem[product_name]["installed_versions"] = controller.get_installed_versions(
                product_name, outout_format="long"
            )
            self.ansys_ecosystem[product_name]["compatible_versions"] = [
                product_version
                for product_version in self.ansys_ecosystem[product_name]["installed_versions"]
                if product_version in self.ansys_ecosystem[product_name]["authorized_versions"]
            ]

            if len(self.ansys_ecosystem[product_name]["installed_versions"]) == 0:
                alert_message = f"No installation of {product_name.title()} found in the machine {platform.node()}."
                alert_color = "danger"
                self.ansys_ecosystem_ready = False
            elif len(self.ansys_ecosystem[product_name]["compatible_versions"]) == 0:
                alert_message = (
                    f"None of the authorized versions of {product_name.title()} "
                    f"is installed in the machine {platform.node()}.\n"
                )
                alert_message += "At least one of these versions is required:"
                for authorized_version in self.ansys_ecosystem[product_name]["authorized_versions"]:
                    self.ansys_ecosystem[product_name][
                        "alert_message"
                    ] += f" {convert_to_long_version(authorized_version)}"
                alert_message += "."
                alert_color = "danger"
                self.ansys_ecosystem_ready = False
            else:
                self.ansys_ecosystem[product_name]["selected_version"] = self.ansys_ecosystem[product_name][
                    "compatible_versions"
                ][
                    -1
                ]  # Latest
                alert_message = f"{product_name.title()} install detected. Compatible versions are:"
                for compatible_version in self.ansys_ecosystem[product_name]["compatible_versions"]:
                    alert_message += f" {convert_to_long_version(compatible_version)}"
                alert_message += ".\n"
                alert_message += "Selected version is %s." % (self.ansys_ecosystem[product_name]["selected_version"])
                alert_color = "success"
            self.ansys_ecosystem[product_name]["alert_message"] = alert_message
            self.ansys_ecosystem[product_name]["alert_color"] = alert_color

    @transaction(
        self=StepSpec(
            download=[
                "project_file",
                "working_properties_file",
                "workbench_input_deck",
                "system_hierarchy_file",
                "tcp_server_stopped_states",
            ],
            upload=[
                "optislang_solve_status",
                "server_info_file",
                "actors_info",
                "actors_status_info",
                "tcp_server_port",
                "project_status_info",
                "results_files",
                "results_directory",
            ],
        )
    )
    @long_running
    def start_analysis(self) -> None:
        """Start optiSLang and run the project."""

        self.system_hierarchy = read_system_hierarchy(self.system_hierarchy_file.path)

        osl = Optislang(
            project_path=self.project_file.path,
            loglevel="DEBUG",
            reset=True,
            shutdown_on_finished=True,
            import_project_properties_file=self.working_properties_file.path,
            additional_args=[f"--write-server-info={self.server_info_file.path}"],
            ini_timeout=30,  # might need to be adjusted
        )

        if self.tcp_server_port is None:
            if self.server_info_file.exists():
                with open(self.server_info_file.path, "r") as file:
                    lines = [line.rstrip("\n") for line in file.readlines()]
                for line in lines:
                    if line.startswith("server_port="):
                        self.tcp_server_port = int(line.split("=")[1])
                        break
            else:
                raise Exception("No server info file detected. Unable to retrieve TCP port number.")

        osl.start(wait_for_started=True, wait_for_finished=False)

        while True:
            # Get project status info
            self.project_status_info = osl.get_osl_server().get_full_project_status_info()
            # Get actor status info
            for node_info in self.system_hierarchy:
                self.actors_info[node_info["uid"]] = osl.get_osl_server().get_actor_info(node_info["uid"])
                node_hids = _get_actor_hids(osl.get_osl_server().get_actor_states(node_info["uid"]))
                if len(node_hids):
                    self.actors_status_info[node_info["uid"]] = []
                    for hid in node_hids:
                        self.actors_status_info[node_info["uid"]].append(
                            osl.get_osl_server().get_actor_status_info(node_info["uid"], hid)
                        )
            # Get status
            self.optislang_solve_status = osl.project.get_status().lower()
            # Upload fields
            self.transaction.upload(["optislang_solve_status"])
            self.transaction.upload(["project_status_info"])
            self.transaction.upload(["actors_info"])
            self.transaction.upload(["actors_status_info"])
            # Check if analysis stopped
            if self.optislang_solve_status in self.tcp_server_stopped_states:
                break
            time.sleep(3)

        osl.dispose()
