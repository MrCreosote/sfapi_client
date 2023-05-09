import os
import re
from pathlib import Path
import json

import typer
import unasync
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from typing import List, Optional

from datamodel_code_generator import InputFileType, generate
import typer


cli = typer.Typer()


#
# Generate sync client using unasync
#
@cli.command(name="unasync")
def run_unasync():
    additional_replacements = {
        "AsyncClient": "Client",
        "AsyncApi": "Api",
        "AsyncResources": "Resources",
        "AsyncCompute": "Compute",
        "AsyncGroup": "Group",
        "AsyncGroupMember": "GroupMember",
        "AsyncRemotePath": "RemotePath",
        "AsyncProject": "Project",
        "AsyncUser": "User",
        "AsyncJob": "Job",
        "AsyncJobSacct": "JobSacct",
        "AsyncJobSqueue": "JobSqueue",
        "AsyncOAuth2Client": "OAuth2Client",
        "aclose": "close",
        "_ASYNC_SLEEP": "_SLEEP",
    }
    rules = [
        unasync.Rule(
            fromdir="/src/sfapi_client/_async/",
            todir="/src/sfapi_client/_sync/",
            additional_replacements=additional_replacements,
        ),
    ]

    filepaths = []
    exclude = ["common.py"]

    for p in (Path(__file__).parent.parent / "src" / "sfapi_client" / "_async").glob(
        "**/*.py"
    ):
        if p.name not in exclude:
            filepaths.append(str(p))

    unasync.unasync_files(filepaths, rules)

    # unasync doesn't handle docstrings, so do them using regex replace
    subs = [
        ("Async", ""),
        ("await ", ""),
        ("async ", ""),
    ]

    for path in (Path(__file__).parent.parent / "src" / "sfapi_client" / "_sync").glob(
        "**/*.py"
    ):
        if path.name not in exclude:
            with path.open() as fp:
                code = fp.read()

            for target, replacement in subs:
                pattern = re.compile(rf"(.*\"\"\".*){target}(.*\"\"\".*)", re.DOTALL)

                # While we have matches replace them
                modified = False
                while pattern.match(code):
                    code = re.sub(pattern, rf"\1{replacement}\2", code)
                    modified = True

                if modified:
                    with path.open("w") as fp:
                        fp.write(code)


def _from_open_api() -> str:
    with TemporaryDirectory() as tempdir:
        output = Path(tempdir) / "model.py"
        generate(
            use_double_quotes=True,
            input_=urlparse("https://api.nersc.gov/api/v1.2/openapi.json"),
            input_file_type=InputFileType.OpenAPI,
            output=output,
        )

        return output.read_text()


def _from_json(json: Path, class_name: str) -> str:
    with TemporaryDirectory() as tempdir:
        output = Path(tempdir) / "model.py"
        generate(
            use_double_quotes=True,
            force_optional_for_required_fields=True,
            input_=json,
            input_file_type=InputFileType.Json,
            output=output,
            class_name=class_name,
            aliases={
                "OutputItem": "JobStatus",
            },
        )

        return output.read_text()


#
# Generate models using datamodel-codegen using OpenAPI spec and a sample JSON job status output.
# Eventually is would be nice to move the job status model into SF API, so cold then just rely
# only on the OpenAPI spec.
#
@cli.command(name="codegen")
def openapimodel_codegen(
    output: Path = typer.Option(
        Path(__file__).parent.parent
        / "src"
        / "sfapi_client"
        / "_models"
        / "__init__.py",
        dir_okay=False,
        writable=True,
    ),
):
    with output.open("w") as fp:
        fp.write(_from_open_api())


@cli.command(name="datacodegen")
def datamodel_codegen(
    json_models: Optional[List[Path]] = typer.Option(
        None, dir_okay=True, writable=True
    ),
):
    base_dir = Path(__file__).parent.parent / "src" / "sfapi_client" / "_models"
    for model in json_models:
        model = model.resolve(strict=False)
        output = Path(f"{base_dir}/{model.stem}.py")

        with output.open("w") as fp:
            name_split = model.stem.split("_")
            name_split = [name.capitalize() for name in name_split]
            job_model = _from_json(model, f"{''.join(name_split)}")
            fp.write(job_model)


@cli.command(name="examples")
def work_on_examples(
    replace: Optional[Path] = typer.Option((Path('examples_dev') / "replacement.json"), dir_okay=False),
):
    dev_dir = Path(__file__).parent.parent / "examples_dev"
    dev_dir.mkdir(exist_ok=True)
    examples = (Path(__file__).parent.parent / "examples").glob("*.ipynb")

    if replace.exists():
        with replace.open('r'):
            replacements = json.loads(replace.read_text())
    else:
        replacements = {}

    # Replace personal details in notebook
    for notebook in examples:
        # Read in notebook
        with notebook.open('r') as nb:
            full_nb = nb.read()
        # replace all key with value
        for v, k in replacements.items():
            full_nb = full_nb.replace(k, v)

        new_path = dev_dir / notebook.name
        # Open to write back to notebook
        with new_path.open('w') as nb:
            nb.write(full_nb)


if __name__ == "__main__":
    cli()
