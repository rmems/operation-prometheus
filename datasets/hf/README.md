---
license: other
license_name: mixed-per-record
pretty_name: Operation Prometheus trajectories
tags:
- code
- software-engineering
- pull-requests
- code-review
- trajectories
size_categories:
- n<1K
configs:
- config_name: default
  data_files: trajectories.jsonl
---

# Operation Prometheus — software-engineering trajectories

Pull-request engineering trajectories extracted from public GitHub history by
[operation-prometheus](https://github.com/rmems/operation-prometheus):
issue/review signal → code state → patch → validation → outcome.

- **Records:** 396
- **Format:** JSONL (`trajectories.jsonl`), schema `pr_trajectory_v0` / `trajectory_v1`
- **Languages:** Julia, Python, Rust, SystemVerilog
- **sha256:** `77fe21e75afe5aba…`

## Record fields

`id`, `repo`, `pr_number`, `source_urls`, `language`, `domain`, `task_type`,
`before_context`, `patch`, `validation`, `outcome`, `training_use`,
`issue_context`, `review_signals`, `quality_score`, `source_license`.

`training_use` buckets:

| Bucket | Records |
|--------|---------|
| `bug-prediction` | 3 |
| `feature` | 165 |
| `other` | 22 |
| `repair` | 174 |
| `review-to-patch` | 21 |
| `validation` | 11 |

## Source repositories and license / provenance

Each record's `source_license` is the license of its originating repository —
this dataset is **not** under a single blanket license, which is why the card
declares `license: other` / `mixed-per-record` rather than MIT or Apache-2.0
for the whole. The export tooling and schemas are Apache-2.0; that does not
relicense source-derived content.
License set represented: Apache-2.0; BSD-2-Clause; BSD-3-Clause; MIT; MIT OR Apache-2.0.

| Repository | Records | Source license |
|------------|---------|----------------|
| [1Password/typeshare](https://github.com/1Password/typeshare) | 1 | Apache-2.0 |
| [3Hren/msgpack-rust](https://github.com/3Hren/msgpack-rust) | 1 | MIT |
| [3YOURMIND/django-migration-linter](https://github.com/3YOURMIND/django-migration-linter) | 1 | Apache-2.0 |
| [AcademySoftwareFoundation/rez](https://github.com/AcademySoftwareFoundation/rez) | 1 | Apache-2.0 |
| [AgnostiqHQ/covalent](https://github.com/AgnostiqHQ/covalent) | 1 | Apache-2.0 |
| [Aleph-Alpha/ts-rs](https://github.com/Aleph-Alpha/ts-rs) | 1 | MIT |
| [Azure-Samples/azure-search-openai-demo](https://github.com/Azure-Samples/azure-search-openai-demo) | 1 | MIT |
| [Azure/WALinuxAgent](https://github.com/Azure/WALinuxAgent) | 1 | Apache-2.0 |
| [Azure/azure-sdk-for-rust](https://github.com/Azure/azure-sdk-for-rust) | 1 | MIT |
| [CORE-GATECH-GROUP/serpent-tools](https://github.com/CORE-GATECH-GROUP/serpent-tools) | 1 | MIT |
| [CS-SI/eodag](https://github.com/CS-SI/eodag) | 1 | Apache-2.0 |
| [CSML-by-Clevy/csml-engine](https://github.com/CSML-by-Clevy/csml-engine) | 1 | Apache-2.0 |
| [CTFd/CTFd](https://github.com/CTFd/CTFd) | 1 | Apache-2.0 |
| [CodeForPhilly/chime](https://github.com/CodeForPhilly/chime) | 1 | MIT |
| [CosmWasm/cosmwasm](https://github.com/CosmWasm/cosmwasm) | 1 | Apache-2.0 |
| [CosmWasm/cw-multi-test](https://github.com/CosmWasm/cw-multi-test) | 1 | Apache-2.0 |
| [CrossGL/crosstl](https://github.com/CrossGL/crosstl) | 1 | Apache-2.0 |
| [DA0-DA0/dao-contracts](https://github.com/DA0-DA0/dao-contracts) | 1 | BSD-3-Clause |
| [DataDog/guarddog](https://github.com/DataDog/guarddog) | 1 | Apache-2.0 |
| [Delgan/loguru](https://github.com/Delgan/loguru) | 1 | MIT |
| [Diaoul/subliminal](https://github.com/Diaoul/subliminal) | 1 | MIT |
| [DigitalSlideArchive/HistomicsTK](https://github.com/DigitalSlideArchive/HistomicsTK) | 1 | Apache-2.0 |
| [EducationalTestingService/rsmtool](https://github.com/EducationalTestingService/rsmtool) | 1 | Apache-2.0 |
| [Enselic/cargo-public-api](https://github.com/Enselic/cargo-public-api) | 1 | MIT |
| [Enter-tainer/typstyle](https://github.com/Enter-tainer/typstyle) | 1 | Apache-2.0 |
| [GPflow/GPflow](https://github.com/GPflow/GPflow) | 1 | Apache-2.0 |
| [GREsau/schemars](https://github.com/GREsau/schemars) | 1 | MIT |
| [Galileo-Galilei/kedro-mlflow](https://github.com/Galileo-Galilei/kedro-mlflow) | 1 | Apache-2.0 |
| [GoogleCloudPlatform/cloud-sql-python-connector](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector) | 1 | Apache-2.0 |
| [GoogleCloudPlatform/functions-framework-python](https://github.com/GoogleCloudPlatform/functions-framework-python) | 1 | Apache-2.0 |
| [GoogleCloudPlatform/google-auth-library-python](https://github.com/GoogleCloudPlatform/google-auth-library-python) | 1 | Apache-2.0 |
| [HTTP-APIs/hydrus](https://github.com/HTTP-APIs/hydrus) | 1 | MIT |
| [IAMconsortium/pyam](https://github.com/IAMconsortium/pyam) | 1 | Apache-2.0 |
| [IDSIA/sacred](https://github.com/IDSIA/sacred) | 1 | MIT |
| [JonathonReinhart/scuba](https://github.com/JonathonReinhart/scuba) | 1 | MIT |
| [Keats/tera](https://github.com/Keats/tera) | 1 | MIT |
| [Keats/validator](https://github.com/Keats/validator) | 1 | MIT |
| [Kozea/WeasyPrint](https://github.com/Kozea/WeasyPrint) | 1 | BSD-3-Clause |
| [Leafwing-Studios/leafwing-input-manager](https://github.com/Leafwing-Studios/leafwing-input-manager) | 1 | Apache-2.0 |
| [Limen-Neural/axon-encoder](https://github.com/Limen-Neural/axon-encoder) | 3 | MIT OR Apache-2.0 |
| [Limen-Neural/brainstem-daemon](https://github.com/Limen-Neural/brainstem-daemon) | 4 | MIT OR Apache-2.0 |
| [Limen-Neural/limbic-critic](https://github.com/Limen-Neural/limbic-critic) | 4 | MIT OR Apache-2.0 |
| [Limen-Neural/myelin-accelerator](https://github.com/Limen-Neural/myelin-accelerator) | 5 | MIT OR Apache-2.0 |
| [Limen-Neural/neuromod](https://github.com/Limen-Neural/neuromod) | 5 | MIT OR Apache-2.0 |
| [Limen-Neural/nir-rs](https://github.com/Limen-Neural/nir-rs) | 4 | MIT OR Apache-2.0 |
| [Limen-Neural/synaptic-mesh](https://github.com/Limen-Neural/synaptic-mesh) | 5 | MIT OR Apache-2.0 |
| [ManevilleF/hexx](https://github.com/ManevilleF/hexx) | 1 | Apache-2.0 |
| [ManiacalLabs/BiblioPixel](https://github.com/ManiacalLabs/BiblioPixel) | 1 | MIT |
| [MarcoIeni/release-plz](https://github.com/MarcoIeni/release-plz) | 1 | Apache-2.0 |
| [MarketSquare/robotframework-robocop](https://github.com/MarketSquare/robotframework-robocop) | 1 | Apache-2.0 |
| [MartinThoma/flake8-simplify](https://github.com/MartinThoma/flake8-simplify) | 1 | MIT |
| [Materials-Consortia/optimade-python-tools](https://github.com/Materials-Consortia/optimade-python-tools) | 1 | MIT |
| [MiSawa/xq](https://github.com/MiSawa/xq) | 1 | MIT |
| [Migorithm/duva](https://github.com/Migorithm/duva) | 1 | Apache-2.0 |
| [NCAR/geocat-comp](https://github.com/NCAR/geocat-comp) | 1 | Apache-2.0 |
| [NTNU-IHB/PythonFMU](https://github.com/NTNU-IHB/PythonFMU) | 1 | MIT |
| [Neoteroi/BlackSheep](https://github.com/Neoteroi/BlackSheep) | 1 | MIT |
| [Nukesor/comfy-table](https://github.com/Nukesor/comfy-table) | 1 | MIT |
| [OCR-D/core](https://github.com/OCR-D/core) | 1 | Apache-2.0 |
| [OceanParcels/Parcels](https://github.com/OceanParcels/Parcels) | 1 | MIT |
| [OceanParcels/parcels](https://github.com/OceanParcels/parcels) | 1 | MIT |
| [OpenMDAO/dymos](https://github.com/OpenMDAO/dymos) | 1 | Apache-2.0 |
| [OpenMined/PySyft](https://github.com/OpenMined/PySyft) | 1 | Apache-2.0 |
| [OpenNMT/OpenNMT-tf](https://github.com/OpenNMT/OpenNMT-tf) | 1 | MIT |
| [OpenZeppelin/rust-contracts-stylus](https://github.com/OpenZeppelin/rust-contracts-stylus) | 1 | MIT |
| [Ouranosinc/xclim](https://github.com/Ouranosinc/xclim) | 1 | Apache-2.0 |
| [Parquery/icontract](https://github.com/Parquery/icontract) | 1 | MIT |
| [PennyLaneAI/pennylane](https://github.com/PennyLaneAI/pennylane) | 1 | Apache-2.0 |
| [PlasmaPy/PlasmaPy](https://github.com/PlasmaPy/PlasmaPy) | 1 | BSD-3-Clause |
| [PrefectHQ/prefect-aws](https://github.com/PrefectHQ/prefect-aws) | 1 | Apache-2.0 |
| [PyCQA/bandit](https://github.com/PyCQA/bandit) | 1 | Apache-2.0 |
| [PyCQA/docformatter](https://github.com/PyCQA/docformatter) | 1 | MIT |
| [PyCQA/pyflakes](https://github.com/PyCQA/pyflakes) | 1 | MIT |
| [PyFilesystem/pyfilesystem2](https://github.com/PyFilesystem/pyfilesystem2) | 1 | MIT |
| [PyPSA/linopy](https://github.com/PyPSA/linopy) | 1 | MIT |
| [PyThaiNLP/pythainlp](https://github.com/PyThaiNLP/pythainlp) | 1 | Apache-2.0 |
| [PyVRP/PyVRP](https://github.com/PyVRP/PyVRP) | 1 | MIT |
| [Python-Markdown/markdown](https://github.com/Python-Markdown/markdown) | 1 | BSD-3-Clause |
| [QCHackers/tqec](https://github.com/QCHackers/tqec) | 1 | Apache-2.0 |
| [QCoDeS/Qcodes](https://github.com/QCoDeS/Qcodes) | 1 | MIT |
| [Qiskit-Extensions/circuit-knitting-toolbox](https://github.com/Qiskit-Extensions/circuit-knitting-toolbox) | 1 | Apache-2.0 |
| [Qiskit/qiskit](https://github.com/Qiskit/qiskit) | 1 | Apache-2.0 |
| [Qiskit/qiskit-ibm-runtime](https://github.com/Qiskit/qiskit-ibm-runtime) | 1 | Apache-2.0 |
| [Qiskit/qiskit-terra](https://github.com/Qiskit/qiskit-terra) | 1 | Apache-2.0 |
| [Quansight/ragna](https://github.com/Quansight/ragna) | 1 | BSD-3-Clause |
| [QuantEcon/QuantEcon.py](https://github.com/QuantEcon/QuantEcon.py) | 1 | MIT |
| [Quantum-Accelerators/quacc](https://github.com/Quantum-Accelerators/quacc) | 1 | BSD-3-Clause |
| [RadioAstronomySoftwareGroup/pyuvdata](https://github.com/RadioAstronomySoftwareGroup/pyuvdata) | 1 | BSD-2-Clause |
| [ResearchObject/ro-crate-py](https://github.com/ResearchObject/ro-crate-py) | 1 | Apache-2.0 |
| [SciTools/cartopy](https://github.com/SciTools/cartopy) | 1 | BSD-3-Clause |
| [SciTools/iris](https://github.com/SciTools/iris) | 1 | BSD-3-Clause |
| [Scille/umongo](https://github.com/Scille/umongo) | 1 | MIT |
| [SeaQL/sea-orm](https://github.com/SeaQL/sea-orm) | 1 | Apache-2.0 |
| [SebRut/pygrocy](https://github.com/SebRut/pygrocy) | 1 | MIT |
| [Senth/minecraft-mod-manager](https://github.com/Senth/minecraft-mod-manager) | 1 | MIT |
| [SpikeInterface/spikeinterface](https://github.com/SpikeInterface/spikeinterface) | 1 | MIT |
| [Stebalien/tempfile](https://github.com/Stebalien/tempfile) | 1 | Apache-2.0 |
| [StingraySoftware/stingray](https://github.com/StingraySoftware/stingray) | 1 | MIT |
| [Stranger6667/postmarker](https://github.com/Stranger6667/postmarker) | 1 | MIT |
| [TedDriggs/darling](https://github.com/TedDriggs/darling) | 1 | MIT |
| [Textualize/rich](https://github.com/Textualize/rich) | 1 | MIT |
| [TobikoData/sqlmesh](https://github.com/TobikoData/sqlmesh) | 1 | Apache-2.0 |
| [Toblerity/Shapely](https://github.com/Toblerity/Shapely) | 1 | BSD-3-Clause |
| [USEPA/haztrak](https://github.com/USEPA/haztrak) | 1 | MIT |
| [Unidata/siphon](https://github.com/Unidata/siphon) | 1 | BSD-3-Clause |
| [Unleash/unleash-client-python](https://github.com/Unleash/unleash-client-python) | 1 | MIT |
| [VirtusLab/git-machete](https://github.com/VirtusLab/git-machete) | 1 | MIT |
| [WorksApplications/sudachi.rs](https://github.com/WorksApplications/sudachi.rs) | 1 | Apache-2.0 |
| [XKNX/xknx](https://github.com/XKNX/xknx) | 1 | MIT |
| [XLSForm/pyxform](https://github.com/XLSForm/pyxform) | 1 | BSD-2-Clause |
| [aaugustin/websockets](https://github.com/aaugustin/websockets) | 1 | BSD-3-Clause |
| [ably/ably-python](https://github.com/ably/ably-python) | 1 | Apache-2.0 |
| [actix/actix-web](https://github.com/actix/actix-web) | 1 | Apache-2.0 |
| [adamchainz/flake8-comprehensions](https://github.com/adamchainz/flake8-comprehensions) | 1 | MIT |
| [aeon-toolkit/aeon](https://github.com/aeon-toolkit/aeon) | 1 | BSD-3-Clause |
| [aeye-lab/pymovements](https://github.com/aeye-lab/pymovements) | 1 | MIT |
| [aio-libs/aiosmtpd](https://github.com/aio-libs/aiosmtpd) | 1 | Apache-2.0 |
| [aiogram/aiogram](https://github.com/aiogram/aiogram) | 1 | MIT |
| [airtai/faststream](https://github.com/airtai/faststream) | 1 | Apache-2.0 |
| [alexcrichton/futures-rs](https://github.com/alexcrichton/futures-rs) | 1 | Apache-2.0 |
| [alexcrichton/proc-macro2](https://github.com/alexcrichton/proc-macro2) | 1 | Apache-2.0 |
| [alexcrichton/toml-rs](https://github.com/alexcrichton/toml-rs) | 1 | Apache-2.0 |
| [altair-viz/altair](https://github.com/altair-viz/altair) | 1 | BSD-3-Clause |
| [alteryx/evalml](https://github.com/alteryx/evalml) | 1 | BSD-3-Clause |
| [alteryx/featuretools](https://github.com/alteryx/featuretools) | 1 | BSD-3-Clause |
| [alteryx/woodwork](https://github.com/alteryx/woodwork) | 1 | BSD-3-Clause |
| [amaranth-lang/amaranth](https://github.com/amaranth-lang/amaranth) | 1 | BSD-2-Clause |
| [ambv/black](https://github.com/ambv/black) | 1 | MIT |
| [ansible/tower-cli](https://github.com/ansible/tower-cli) | 1 | Apache-2.0 |
| [apache/datafusion-sqlparser-rs](https://github.com/apache/datafusion-sqlparser-rs) | 1 | Apache-2.0 |
| [apiflask/apiflask](https://github.com/apiflask/apiflask) | 1 | MIT |
| [apollographql/apollo-rs](https://github.com/apollographql/apollo-rs) | 1 | Apache-2.0 |
| [aristanetworks/anta](https://github.com/aristanetworks/anta) | 1 | Apache-2.0 |
| [asdf-format/asdf](https://github.com/asdf-format/asdf) | 1 | BSD-3-Clause |
| [ashleygwilliams/cargo-generate](https://github.com/ashleygwilliams/cargo-generate) | 1 | Apache-2.0 |
| [ashleygwilliams/wasm-pack](https://github.com/ashleygwilliams/wasm-pack) | 1 | Apache-2.0 |
| [asottile/add-trailing-comma](https://github.com/asottile/add-trailing-comma) | 1 | MIT |
| [ast-grep/ast-grep](https://github.com/ast-grep/ast-grep) | 1 | MIT |
| [astanin/python-tabulate](https://github.com/astanin/python-tabulate) | 1 | MIT |
| [astropenguin/xarray-dataclasses](https://github.com/astropenguin/xarray-dataclasses) | 1 | MIT |
| [astropy/ccdproc](https://github.com/astropy/ccdproc) | 1 | BSD-3-Clause |
| [audreyr/cookiecutter](https://github.com/audreyr/cookiecutter) | 1 | BSD-3-Clause |
| [auth0/auth0-python](https://github.com/auth0/auth0-python) | 1 | MIT |
| [aws-quickstart/taskcat](https://github.com/aws-quickstart/taskcat) | 1 | Apache-2.0 |
| [axodotdev/cargo-dist](https://github.com/axodotdev/cargo-dist) | 1 | Apache-2.0 |
| [banesullivan/localtileserver](https://github.com/banesullivan/localtileserver) | 1 | MIT |
| [benchopt/benchopt](https://github.com/benchopt/benchopt) | 1 | BSD-3-Clause |
| [bentoml/BentoML](https://github.com/bentoml/BentoML) | 1 | Apache-2.0 |
| [bikeshedder/deadpool](https://github.com/bikeshedder/deadpool) | 1 | Apache-2.0 |
| [biotite-dev/biotite](https://github.com/biotite-dev/biotite) | 1 | BSD-3-Clause |
| [bitshifter/glam-rs](https://github.com/bitshifter/glam-rs) | 1 | Apache-2.0 |
| [bloomberg/memray](https://github.com/bloomberg/memray) | 1 | Apache-2.0 |
| [bluesky/bluesky](https://github.com/bluesky/bluesky) | 1 | BSD-3-Clause |
| [bluss/arrayvec](https://github.com/bluss/arrayvec) | 1 | Apache-2.0 |
| [bluss/rust-itertools](https://github.com/bluss/rust-itertools) | 1 | Apache-2.0 |
| [boto/botocore](https://github.com/boto/botocore) | 1 | Apache-2.0 |
| [box/box-python-sdk](https://github.com/box/box-python-sdk) | 1 | Apache-2.0 |
| [brazilian-utils/brutils-python](https://github.com/brazilian-utils/brutils-python) | 1 | MIT |
| [brendanzab/codespan](https://github.com/brendanzab/codespan) | 1 | Apache-2.0 |
| [brettcannon/gidgethub](https://github.com/brettcannon/gidgethub) | 1 | Apache-2.0 |
| [bytecodealliance/wasm-tools](https://github.com/bytecodealliance/wasm-tools) | 1 | Apache-2.0 |
| [bytecodealliance/wasmtime](https://github.com/bytecodealliance/wasmtime) | 1 | Apache-2.0 |
| [cachix/devenv](https://github.com/cachix/devenv) | 1 | Apache-2.0 |
| [caikit/caikit](https://github.com/caikit/caikit) | 1 | Apache-2.0 |
| [callowayproject/bump-my-version](https://github.com/callowayproject/bump-my-version) | 1 | MIT |
| [canonical/operator](https://github.com/canonical/operator) | 1 | Apache-2.0 |
| [capitalone/datacompy](https://github.com/capitalone/datacompy) | 1 | Apache-2.0 |
| [cargo-generate/cargo-generate](https://github.com/cargo-generate/cargo-generate) | 1 | Apache-2.0 |
| [cedar-policy/cedar](https://github.com/cedar-policy/cedar) | 1 | Apache-2.0 |
| [cekit/cekit](https://github.com/cekit/cekit) | 1 | MIT |
| [census-instrumentation/opencensus-python](https://github.com/census-instrumentation/opencensus-python) | 1 | Apache-2.0 |
| [chezou/tabula-py](https://github.com/chezou/tabula-py) | 1 | MIT |
| [clap-rs/clap](https://github.com/clap-rs/clap) | 1 | Apache-2.0 |
| [cloudant/python-cloudant](https://github.com/cloudant/python-cloudant) | 1 | Apache-2.0 |
| [cloudtools/troposphere](https://github.com/cloudtools/troposphere) | 1 | BSD-2-Clause |
| [cobalt-org/cobalt.rs](https://github.com/cobalt-org/cobalt.rs) | 1 | Apache-2.0 |
| [cobalt-org/liquid-rust](https://github.com/cobalt-org/liquid-rust) | 1 | MIT |
| [cogent3/cogent3](https://github.com/cogent3/cogent3) | 1 | BSD-3-Clause |
| [conan-io/conan](https://github.com/conan-io/conan) | 1 | MIT |
| [conan-io/conan-package-tools](https://github.com/conan-io/conan-package-tools) | 1 | MIT |
| [conda-incubator/grayskull](https://github.com/conda-incubator/grayskull) | 1 | Apache-2.0 |
| [copier-org/copier](https://github.com/copier-org/copier) | 1 | MIT |
| [cornellius-gp/gpytorch](https://github.com/cornellius-gp/gpytorch) | 1 | MIT |
| [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | 1 | MIT |
| [crossbeam-rs/crossbeam](https://github.com/crossbeam-rs/crossbeam) | 1 | Apache-2.0 |
| [crsmithdev/arrow](https://github.com/crsmithdev/arrow) | 1 | Apache-2.0 |
| [cta-observatory/ctapipe](https://github.com/cta-observatory/ctapipe) | 1 | BSD-3-Clause |
| [cubed-dev/cubed](https://github.com/cubed-dev/cubed) | 1 | Apache-2.0 |
| [cuthbertLab/music21](https://github.com/cuthbertLab/music21) | 1 | BSD-3-Clause |
| [d0c-s4vage/pfp](https://github.com/d0c-s4vage/pfp) | 1 | MIT |
| [dask-contrib/dask-expr](https://github.com/dask-contrib/dask-expr) | 1 | BSD-3-Clause |
| [dask/dask](https://github.com/dask/dask) | 1 | BSD-3-Clause |
| [dask/dask-jobqueue](https://github.com/dask/dask-jobqueue) | 1 | BSD-3-Clause |
| [databricks/dbt-databricks](https://github.com/databricks/dbt-databricks) | 1 | Apache-2.0 |
| [dataversioncontrol/dvc](https://github.com/dataversioncontrol/dvc) | 1 | Apache-2.0 |
| [davidlattimore/wild](https://github.com/davidlattimore/wild) | 1 | Apache-2.0 |
| [dbrgn/tealdeer](https://github.com/dbrgn/tealdeer) | 1 | Apache-2.0 |
| [dbt-athena/dbt-athena](https://github.com/dbt-athena/dbt-athena) | 1 | Apache-2.0 |
| [dbt-labs/dbt-bigquery](https://github.com/dbt-labs/dbt-bigquery) | 1 | Apache-2.0 |
| [dbt-labs/dbt-redshift](https://github.com/dbt-labs/dbt-redshift) | 1 | Apache-2.0 |
| [dbt-labs/dbt-snowflake](https://github.com/dbt-labs/dbt-snowflake) | 1 | Apache-2.0 |
| [dcs4cop/xcube](https://github.com/dcs4cop/xcube) | 1 | MIT |
| [deepmind/optax](https://github.com/deepmind/optax) | 1 | Apache-2.0 |
| [developmentseed/titiler](https://github.com/developmentseed/titiler) | 1 | MIT |
| [dfinity/sdk](https://github.com/dfinity/sdk) | 1 | Apache-2.0 |
| [digitalocean/pynetbox](https://github.com/digitalocean/pynetbox) | 1 | Apache-2.0 |
| [django-extensions/django-extensions](https://github.com/django-extensions/django-extensions) | 1 | MIT |
| [django/channels](https://github.com/django/channels) | 1 | BSD-3-Clause |
| [djc/askama](https://github.com/djc/askama) | 1 | Apache-2.0 |
| [dotenv-linter/dotenv-linter](https://github.com/dotenv-linter/dotenv-linter) | 1 | MIT |
| [dprint/dprint-plugin-typescript](https://github.com/dprint/dprint-plugin-typescript) | 1 | MIT |
| [dtolnay/anyhow](https://github.com/dtolnay/anyhow) | 1 | Apache-2.0 |
| [dtolnay/async-trait](https://github.com/dtolnay/async-trait) | 1 | Apache-2.0 |
| [dtolnay/cxx](https://github.com/dtolnay/cxx) | 1 | Apache-2.0 |
| [dtolnay/paste](https://github.com/dtolnay/paste) | 1 | Apache-2.0 |
| [dtolnay/syn](https://github.com/dtolnay/syn) | 1 | Apache-2.0 |
| [dtolnay/thiserror](https://github.com/dtolnay/thiserror) | 1 | Apache-2.0 |
| [embassy-rs/embassy](https://github.com/embassy-rs/embassy) | 1 | Apache-2.0 |
| [emit-rs/emit](https://github.com/emit-rs/emit) | 1 | Apache-2.0 |
| [extendr/extendr](https://github.com/extendr/extendr) | 1 | MIT |
| [farcaster-project/farcaster-node](https://github.com/farcaster-project/farcaster-node) | 1 | MIT |
| [fitzgen/bumpalo](https://github.com/fitzgen/bumpalo) | 1 | Apache-2.0 |
| [fujiapple852/trippy](https://github.com/fujiapple852/trippy) | 1 | Apache-2.0 |
| [gfx-rs/wgpu](https://github.com/gfx-rs/wgpu) | 1 | Apache-2.0 |
| [gimli-rs/object](https://github.com/gimli-rs/object) | 1 | Apache-2.0 |
| [gleam-lang/gleam](https://github.com/gleam-lang/gleam) | 1 | Apache-2.0 |
| [gluesql/gluesql](https://github.com/gluesql/gluesql) | 1 | Apache-2.0 |
| [godot-rust/godot-rust](https://github.com/godot-rust/godot-rust) | 1 | MIT |
| [google/argh](https://github.com/google/argh) | 1 | BSD-3-Clause |
| [google/autocxx](https://github.com/google/autocxx) | 1 | Apache-2.0 |
| [huff-language/huff-rs](https://github.com/huff-language/huff-rs) | 1 | Apache-2.0 |
| [hyperium/hyper](https://github.com/hyperium/hyper) | 1 | MIT |
| [image-rs/image-tiff](https://github.com/image-rs/image-tiff) | 1 | MIT |
| [jugglerchris/rust-html2text](https://github.com/jugglerchris/rust-html2text) | 1 | MIT |
| [kbknapp/clap-rs](https://github.com/kbknapp/clap-rs) | 1 | Apache-2.0 |
| [keep-starknet-strange/beerus](https://github.com/keep-starknet-strange/beerus) | 1 | MIT |
| [knope-dev/knope](https://github.com/knope-dev/knope) | 1 | MIT |
| [knurling-rs/defmt](https://github.com/knurling-rs/defmt) | 1 | Apache-2.0 |
| [maciejhirsz/json-rust](https://github.com/maciejhirsz/json-rust) | 1 | Apache-2.0 |
| [martinohmann/hcl-rs](https://github.com/martinohmann/hcl-rs) | 1 | Apache-2.0 |
| [mehcode/config-rs](https://github.com/mehcode/config-rs) | 1 | Apache-2.0 |
| [microsoft/qsharp](https://github.com/microsoft/qsharp) | 1 | MIT |
| [mitsuhiko/insta](https://github.com/mitsuhiko/insta) | 1 | Apache-2.0 |
| [mitsuhiko/minijinja](https://github.com/mitsuhiko/minijinja) | 1 | Apache-2.0 |
| [mozilla/cargo-vet](https://github.com/mozilla/cargo-vet) | 1 | Apache-2.0 |
| [myelin-ai/mockiato](https://github.com/myelin-ai/mockiato) | 1 | MIT |
| [near/borsh-rs](https://github.com/near/borsh-rs) | 1 | Apache-2.0 |
| [netwo-io/apistos](https://github.com/netwo-io/apistos) | 1 | MIT |
| [nix-community/nixpkgs-fmt](https://github.com/nix-community/nixpkgs-fmt) | 1 | Apache-2.0 |
| [not-fl3/nanoserde](https://github.com/not-fl3/nanoserde) | 1 | Apache-2.0 |
| [novifinancial/opaque-ke](https://github.com/novifinancial/opaque-ke) | 1 | Apache-2.0 |
| [nushell/engine-q](https://github.com/nushell/engine-q) | 1 | MIT |
| [oasisprotocol/oasis-sdk](https://github.com/oasisprotocol/oasis-sdk) | 1 | Apache-2.0 |
| [orhun/git-cliff](https://github.com/orhun/git-cliff) | 1 | Apache-2.0 |
| [oxc-project/oxc-resolver](https://github.com/oxc-project/oxc-resolver) | 1 | MIT |
| [pacak/bpaf](https://github.com/pacak/bpaf) | 1 | Apache-2.0 |
| [paritytech/ink](https://github.com/paritytech/ink) | 1 | Apache-2.0 |
| [paritytech/parity-common](https://github.com/paritytech/parity-common) | 1 | Apache-2.0 |
| [pest-parser/pest](https://github.com/pest-parser/pest) | 1 | Apache-2.0 |
| [polarity-lang/polarity](https://github.com/polarity-lang/polarity) | 1 | Apache-2.0 |
| [posit-dev/air](https://github.com/posit-dev/air) | 1 | MIT |
| [projectfluent/fluent-rs](https://github.com/projectfluent/fluent-rs) | 1 | Apache-2.0 |
| [public-awesome/launchpad](https://github.com/public-awesome/launchpad) | 1 | Apache-2.0 |
| [pulldown-cmark/pulldown-cmark](https://github.com/pulldown-cmark/pulldown-cmark) | 1 | MIT |
| [pyfisch/cbor](https://github.com/pyfisch/cbor) | 1 | Apache-2.0 |
| [quartiq/minimq](https://github.com/quartiq/minimq) | 1 | MIT |
| [railwayapp/nixpacks](https://github.com/railwayapp/nixpacks) | 1 | MIT |
| [raphlinus/pulldown-cmark](https://github.com/raphlinus/pulldown-cmark) | 1 | MIT |
| [rayon-rs/rayon](https://github.com/rayon-rs/rayon) | 1 | Apache-2.0 |
| [rcoh/angle-grinder](https://github.com/rcoh/angle-grinder) | 1 | MIT |
| [reubeno/brush](https://github.com/reubeno/brush) | 1 | MIT |
| [rmems/LiquidCortex.jl](https://github.com/rmems/LiquidCortex.jl) | 3 | MIT OR Apache-2.0 |
| [rmems/SpikeStream.jl](https://github.com/rmems/SpikeStream.jl) | 4 | MIT OR Apache-2.0 |
| [rmems/Theseus-Quarry](https://github.com/rmems/Theseus-Quarry) | 5 | MIT |
| [rmems/agoge-forger](https://github.com/rmems/agoge-forger) | 4 | Apache-2.0 |
| [rmems/corinth-canal](https://github.com/rmems/corinth-canal) | 12 | MIT OR Apache-2.0 |
| [rmems/engram-parser](https://github.com/rmems/engram-parser) | 1 | MIT OR Apache-2.0 |
| [rmems/grok-ozempic](https://github.com/rmems/grok-ozempic) | 12 | MIT OR Apache-2.0 |
| [rmems/kinetic-signals](https://github.com/rmems/kinetic-signals) | 5 | MIT OR Apache-2.0 |
| [rmems/silicon-hdl](https://github.com/rmems/silicon-hdl) | 5 | MIT OR Apache-2.0 |
| [rmems/spike-viz](https://github.com/rmems/spike-viz) | 3 | Apache-2.0 |
| [rmems/thalamic-relay](https://github.com/rmems/thalamic-relay) | 3 | MIT OR Apache-2.0 |
| [rmems/writ](https://github.com/rmems/writ) | 5 | Apache-2.0 |
| [rmems/xai-dissect](https://github.com/rmems/xai-dissect) | 4 | MIT OR Apache-2.0 |
| [ron-rs/ron](https://github.com/ron-rs/ron) | 1 | Apache-2.0 |
| [ruma/ruma](https://github.com/ruma/ruma) | 1 | MIT |
| [rust-analyzer/rust-analyzer](https://github.com/rust-analyzer/rust-analyzer) | 1 | Apache-2.0 |
| [rust-itertools/itertools](https://github.com/rust-itertools/itertools) | 1 | Apache-2.0 |
| [rust-lang-nursery/futures-rs](https://github.com/rust-lang-nursery/futures-rs) | 1 | Apache-2.0 |
| [rust-lang/annotate-snippets-rs](https://github.com/rust-lang/annotate-snippets-rs) | 1 | Apache-2.0 |
| [rust-lang/cc-rs](https://github.com/rust-lang/cc-rs) | 1 | Apache-2.0 |
| [rust-lang/futures-rs](https://github.com/rust-lang/futures-rs) | 1 | Apache-2.0 |
| [rust-lang/regex](https://github.com/rust-lang/regex) | 1 | Apache-2.0 |
| [rust-lang/rust-analyzer](https://github.com/rust-lang/rust-analyzer) | 1 | Apache-2.0 |
| [rust-lang/rust-bindgen](https://github.com/rust-lang/rust-bindgen) | 1 | BSD-3-Clause |
| [rust-lang/rustfmt](https://github.com/rust-lang/rustfmt) | 1 | Apache-2.0 |
| [rust-ndarray/ndarray](https://github.com/rust-ndarray/ndarray) | 1 | Apache-2.0 |
| [rust-phf/rust-phf](https://github.com/rust-phf/rust-phf) | 1 | MIT |
| [rust-random/getrandom](https://github.com/rust-random/getrandom) | 1 | Apache-2.0 |
| [rustwasm/wasm-pack](https://github.com/rustwasm/wasm-pack) | 1 | Apache-2.0 |
| [sagebind/isahc](https://github.com/sagebind/isahc) | 1 | MIT |
| [salsa-rs/salsa](https://github.com/salsa-rs/salsa) | 1 | Apache-2.0 |
| [scylladb/scylla-rust-driver](https://github.com/scylladb/scylla-rust-driver) | 1 | Apache-2.0 |
| [seaofvoices/darklua](https://github.com/seaofvoices/darklua) | 1 | MIT |
| [servo/rust-url](https://github.com/servo/rust-url) | 1 | Apache-2.0 |
| [sfackler/rust-postgres](https://github.com/sfackler/rust-postgres) | 1 | Apache-2.0 |
| [sharkdp/fd](https://github.com/sharkdp/fd) | 1 | Apache-2.0 |
| [sharkdp/numbat](https://github.com/sharkdp/numbat) | 1 | Apache-2.0 |
| [shepmaster/snafu](https://github.com/shepmaster/snafu) | 1 | Apache-2.0 |
| [static-web-server/static-web-server](https://github.com/static-web-server/static-web-server) | 1 | Apache-2.0 |
| [stellar/rs-soroban-env](https://github.com/stellar/rs-soroban-env) | 1 | Apache-2.0 |
| [sunng87/handlebars-rust](https://github.com/sunng87/handlebars-rust) | 1 | MIT |
| [swellaby/rusty-hook](https://github.com/swellaby/rusty-hook) | 1 | MIT |
| [tafia/quick-xml](https://github.com/tafia/quick-xml) | 1 | MIT |
| [taiki-e/cargo-hack](https://github.com/taiki-e/cargo-hack) | 1 | Apache-2.0 |
| [tokio-rs/bytes](https://github.com/tokio-rs/bytes) | 1 | MIT |
| [tokio-rs/mio](https://github.com/tokio-rs/mio) | 1 | MIT |
| [tweag/nickel](https://github.com/tweag/nickel) | 1 | MIT |
| [typst/hayagriva](https://github.com/typst/hayagriva) | 1 | Apache-2.0 |
| [wafflespeanut/paperclip](https://github.com/wafflespeanut/paperclip) | 1 | Apache-2.0 |

## Intended use

SFT / process-supervision for coding agents: feature implementation, repair,
validation discipline, and especially **review-to-patch** — responding to human
review comments with corrective commits.

## Exclusions and limitations

Per the [data policy](https://github.com/rmems/operation-prometheus/blob/main/docs/data-policy.md):
no secrets, private configs, model weights, closed-model chat logs, or bot
boilerplate (review bots like Gemini/Codex are retained as signal). Large
patches may be truncated (~96 KiB cap). Solo-maintainer repos: limited
multi-human review. Inspect records before training use.
