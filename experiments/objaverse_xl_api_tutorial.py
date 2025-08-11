# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.17.1
#   kernelspec:
#     display_name: sb
#     language: python
#     name: python3
# ---

# %% [markdown] id="zn7g17hc3ADi"
# # Objaverse-XL API Tutorial
#
# Objaverse-XL is a Universe of 10M+ 3D Objects.
#
# It is hosted on 🤗[Hugging Face](https://huggingface.co/datasets/allenai/objaverse-xl) and includes a [Python API on GitHub](https://github.com/allenai/objaverse-xl). This notebook provides a tutorial on downloading objects and annotations!
#
# We'll get started by downloading the `objaverse` package from PyPi, which will allow us to easily download subsets of the dataset:

# %% colab={"base_uri": "https://localhost:8080/", "height": 89} id="wLB-BPGqGi2e" outputId="b53bf6e2-0a7d-49cd-8e70-be4e397687dc"
# !pip install objaverse --upgrade --quiet

import objaverse
objaverse.__version__

# %% [markdown] id="Z_ScQKLpIGcg"
# The Objaverse-XL API is in the `xl` submodule. Here we'll import it as use the shorthand `oxl` to refer to it:

# %% id="ReHu30YoIvcj"
import objaverse.xl as oxl

# %% [markdown] id="o9QT9O3I4KfV"
# ## Annotations
#
# The objects that appear in the dataset can be obtained with the `get_annotations` function:
#
# ```python
# oxl.get_annotations(
#     download_dir: str = "~/.objaverse",
# ) -> pd.DataFrame
# ```
#
# The function takes in a parameter for `download_dir: str = "~/.objaverse"`, which is the directory to cache the downloaded annotations. After the annotations are downloaded for the first time, they do not need to be downloaded again, as they are cached.
#
# For example:

# %% colab={"base_uri": "https://localhost:8080/", "height": 862} id="t9WbOh0m4kDo" outputId="e7eb921c-1fb9-40d6-b637-02de536b6d9a"
annotations = oxl.get_annotations(
    download_dir="~/.objaverse" # default download directory
)
annotations

# %% [markdown] id="bItU8CwCH8e9"
# > Note: Some objects are still under review for being publicly released.
#
# Here, `annotations` is a pandas DataFrame. These annotations are meant to provide a minimal amount of information about the objects that are standarized across each source and allow it to be downloaded. Each object is a row, and has attributes for:
# - `fileIdentifier` - A unique identifier of the 3D object. Typically the URL that links back to the object.
# - `source` - The website where the 3D object comes from.
# - `license` - The license that the original object was distributed under.
# - `fileType` - The 3D file type of the object (e.g., `fbx`, `obj`, `glb`).
# - `sha256` - The cryptographic hash of the contents of the object (used for deduplication and to check if the object has not been modified since the dataset was originally released).
# - `metadata` - Additional metadata of the object that might be site specific (e.g., the file name). To keep the `annotations` DataFrame lightweight, more detailed annotations may be available as standalone functions (e.g., `objaverse.load_lvis_annotations()`). See the Objaverse 1.0 documentation for more specific annotations.
#
# Since the annotations is a pandas DataFrame object, we can do standard operations on it, such as getting the value counts of different attributes:

# %% colab={"base_uri": "https://localhost:8080/"} id="lBMl0PGGdKmP" outputId="21d6408c-59f5-45d0-8123-6768ef6fd92c"
annotations["source"].value_counts()

# %% colab={"base_uri": "https://localhost:8080/"} id="yDTCdD19Ld9v" outputId="e5687504-4a5b-4c7b-d52d-7eb5c3d45a96"
annotations["fileType"].value_counts()

# %% [markdown] id="EKbyCW04L2NZ"
# And randomly sample objects:

# %% colab={"base_uri": "https://localhost:8080/", "height": 452} id="YpTXV8ysL6oP" outputId="9ba11c1a-8c30-4db3-9f12-76bfdc3141dd"
annotations.sample(5)

# %% [markdown] id="g1UvfZd8AXil"
# ## Alignment Fine-tuning Annotations
#
# For training Zero123-XL, we first started by training on the entire dataset, and then performed fine-tuning on a smaller, more high-quality 3D dataset. To load in the dataset that was used for fine-tuning, we can run:

# %% colab={"base_uri": "https://localhost:8080/", "height": 792} id="4S_yqHYLAz8p" outputId="7ff1476f-07af-4e9f-cc17-d8ba253a9699"
alignment_annotations = oxl.get_alignment_annotations(
    download_dir="~/.objaverse" # default download directory
)
alignment_annotations

# %% [markdown] id="QMgh8o7KQmK0"
# ## Download Objects
#
# Downloading objects can be done through the `download_objects` function:
#
# ```python
# oxl.download_objects(
#     # Base parameters:
#     objects: pd.DataFrame,
#     download_dir: str = "~/.objaverse",
#     processes: Optional[int] = None,  # None => multiprocessing.cpu_count()
#
#     # optional callback functions:
#     handle_found_object: Optional[Callable] = None,
#     handle_modified_object: Optional[Callable] = None,
#     handle_missing_object: Optional[Callable] = None,
#
#     # GitHub specific:
#     save_repo_format: Optional[Literal["zip", "tar", "tar.gz", "files"]] = None,
#     handle_new_object: Optional[Callable] = None,
# )
# ```
#
# The function supports several different types of parameters, which we've broken down into base parameters, callback functions, and GitHub specific parameters.
#
# **Base parameters.**
#
# - `objects: pd.DataFrame` a pandas DataFrame the objects to download. Must have columns for the object "fileIdentifier", "source", and "sha256". Use the `oxl.get_annotations` function to get all objects as a DataFrame.
# - `download_dir: Optional[str] = "~/.objaverse"` specifies where to download the objects.
#
#     Thanks to fsspec, we support writing files to many file systems. To use it, simply use the prefix of your filesystem before the path. For example hdfs://, s3://, http://, gcs://, or ssh://. Some of these file systems require installing an additional package (for example s3fs for s3, gcsfs for gcs, fsspec/sshfs for ssh). Start [here](https://github.com/rom1504/img2dataset#file-system-support) for more details on fsspec.
#
#     If None, the objects will be deleted after they are downloaded. Defaults to "~/.objaverse".
# - `processes: Optional[int] = None` number of processes to use when downloading the objects. If None, it will use the number of CPUs on the machine (which comes from `multiprocessing.cpu_count()`). Defaults to None.
#
# **Callback function parameters.**
# The function also supports several callback functions, which are called right after an object is locally downloaded. Common use cases for these callback functions may include downloading objects on the fly and processing them with Blender, rendering them, then discarding them. The specific callback functions include:
#
# - `handle_found_object: Optional[Callable] = None` is called when an object is successfully found and downloaded. Here, the object has the same sha256 as the one that was downloaded with Objaverse-XL. If None, the object will be downloaded, but nothing will be done with it.
#
#   Parameters for the function must include:
#     - `local_path: str` Local path to the downloaded 3D object.
#     - `file_identifier: str` File identifier of the 3D object.
#     - `sha256: str` sha256 of the contents of the 3D object.
#     - `metadata: Dict[Hashable, Any]` Metadata about the 3D object, such as the GitHub organization and repo name.
#
#   The return of the function is not used.
#
# - `handle_modified_object: Optional[Callable] = None` is called when a modified object is found and downloaded. Here, the object is successfully downloaded, but it has a different sha256 than the one that was downloaded with Objaverse-XL. This is not expected to happen very often, because the same commit hash is used for each repo. If None, the object will be downloaded, but nothing will be done with it.
#
#     Parameters for the function must include:
#     - `local_path: str` Local path to the downloaded 3D object.
#     - `file_identifier: str` File identifier of the 3D object.
#     - `new_sha256: str` sha256 of the contents of the newly downloaded 3D object.
#     - `old_sha256: str` Provided sha256 representing the contents of the 3D object as it was originally intended to be downloaded (coming from the `objects` argument).
#     - `metadata: Dict[Hashable, Any]` Metadata about the 3D object, such as the GitHub organization and repo name.
#
#   The return of the function is not used.
#
# - `handle_missing_object: Optional[Callable] = None` is called when a specified object cannot be found. Here, it is likely that the object was deleted or the repository was deleted or renamed. If None, nothing will be done with the missing object.
#
#     Parameters for the function must include:
#     - `file_identifier: str` File identifier of the 3D object.
#     - `sha256: str` Provided sha256 representing the contents of the 3D object as it was originally intended to be downloaded (coming from the `objects` argument).
#     - `metadata: Dict[Hashable, Any]` Metadata about the 3D object, which is particular to the source.
#
#   The return of the function is not used.
#
# **GitHub specific parameters.** There are several parameters that are only used when downloading objects from GitHub. These parameters can still be passed in when downloading objects from other sources, but they will not be used. These parameters include:
#
# - `save_repo_format: Optional[Literal["zip", "tar", "tar.gz", "files"]] = None` specifies the format to save the GitHub repository. Unlike other sources, GitHub objects are not standalone 3D files, and may link to other assets, such as textures. If None, the repository will not be saved. If "files" is specified, each file will be saved individually in a standard folder structure. Otherwise, the repository can be saved as a "zip", "tar", or "tar.gz" file. Defaults to None.
#
# - `handle_new_object: Optional[Callable]` is called when a new object is found. Here, the object is not used in Objaverse-XL, but is still downloaded as part of the repository. Note that the object may have not been used because it does not successfully import into Blender. If None, the object will be downloaded, but nothing will be done with it.
#
#     Parameters for the function must include:
#     - `local_path: str` Local path to the downloaded 3D object.
#     - `file_identifier: str` GitHub URL of the 3D object.
#     - `sha256: str` sha256 of the contents of the 3D object.
#     - `metadata: Dict[str, Any]` Metadata about the 3D object, such as the GitHub organization and repo names.
#
#   The return of the function is not used.
#
#
# The following is a minimal example of using `oxl.download_objects`:

# %% colab={"base_uri": "https://localhost:8080/", "height": 368} id="SOK_pwa6QniO" outputId="fb447f63-8288-4be8-959e-b15d4b9c9c4c"
# sample a single object from each source
sampled_df = annotations.groupby('source').apply(lambda x: x.sample(1)).reset_index(drop=True)
sampled_df

# %% colab={"base_uri": "https://localhost:8080/"} id="WTJlXqx6vf_m" outputId="fb827183-475c-4c0b-94c2-edf925688d40"
oxl.download_objects(objects=sampled_df)

# %% [markdown] id="BgIq6nc7_T4E"
# Great! As we can see, the objects were successfully downloaded. Note that the GitHub objects were not saved, since `save_repo_format` defaults to None, so they are not included in the output return.
#
# Next, we'll show an example using callback functions, which work well when downloading and processing GitHub objects.
#
# We'll start by removing the `~/.objaverse` directory to clear the cache of the objects that we just downloaded, so they'll be downloaded again from scratch. Otherwise, the objects will be cached and not downloaded for a 2nd time:

# %% id="iedQMatWB8_C"
import shutil
import os

# shutil.rmtree(os.path.expanduser("~/.objaverse"), ignore_errors=True)

# %% [markdown] id="PGTQU78WCQl2"
# And we'll define our `handle_found_object` function, which is called after an object is downloaded and has a sha256 that matches the one that we supplied:

# %% id="gfLIKGTo_Koa"
from typing import Any, Dict, Hashable

def handle_found_object(
    local_path: str,
    file_identifier: str,
    sha256: str,
    metadata: Dict[Hashable, Any]
) -> None:
    print("\n\n\n---HANDLE_FOUND_OBJECT CALLED---\n",
          f"  {local_path=}\n  {file_identifier=}\n  {sha256=}\n  {metadata=}\n\n\n")


# %% [markdown] id="jCbvO89wBM0h"
# Now, after running the same function with the `handle_found_object` callback, we have:

# %% colab={"base_uri": "https://localhost:8080/"} id="BW7v9PG9BMQJ" outputId="27193ae3-1bfb-4df5-81e4-c8be1853d57e"
oxl.download_objects(
    objects=sampled_df,
    handle_found_object=handle_found_object
)

# %% [markdown] id="CTKKLBeMCupZ"
# Notice that our custom `handle_found_object` function is called right after each object is locally downloaded!
#
# Next, for the `handle_modified_object` callback, let's change the sha256 of one of the objects and then try to download it:

# %% colab={"base_uri": "https://localhost:8080/", "height": 348} id="0hrLiVQjLZUI" outputId="23c63dad-d95a-4231-d51a-c1be8f7daa14"
modified_df = sampled_df.copy()
modified_df.iloc[0]["sha256"] = "modified-sha256"
modified_df


# %% id="qnZw-_PNBqen"
def handle_modified_object(
    local_path: str,
    file_identifier: str,
    new_sha256: str,
    old_sha256: str,
    metadata: Dict[Hashable, Any],
) -> None:
    print("\n\n\n---HANDLE_MODIFIED_OBJECT CALLED---\n",
          f"  {local_path=}\n  {file_identifier=}\n  {old_sha256=}\n  {new_sha256}\n  {metadata=}\n\n\n")


# %% colab={"base_uri": "https://localhost:8080/"} id="Qorlg72dLmZx" outputId="7f4961b9-51e9-4d5c-f852-b499fed1ce3e"
# remove previously downloaded objects
shutil.rmtree(os.path.expanduser("~/.objaverse"), ignore_errors=True)

# redownload
oxl.download_objects(
    objects=modified_df,
    handle_found_object=handle_found_object,
    handle_modified_object=handle_modified_object  # <---------------
)

# %% [markdown] id="98DdsLdbRZ3c"
# Notice that `handle_found_object` was called 3 times and `handle_modified_object` was called once, for the object that has its sha256 modified!
#
# We'll do something similar to experiment with `handle_missing_object`, where we'll add modify the path of one of the objects to something that doesn't exist:

# %% colab={"base_uri": "https://localhost:8080/", "height": 386} id="MicUmnDaRXyJ" outputId="b5d84aaa-7bd1-4a81-c2b9-c010d79be2dc"
missing_df = sampled_df.copy()
missing_df.iloc[1]["fileIdentifier"] += "-i-do-not-exist"

print(missing_df.iloc[1]["fileIdentifier"])
missing_df


# %% id="XZ9DbSWjLu31"
def handle_missing_object(
    file_identifier: str,
    sha256: str,
    metadata: Dict[Hashable, Any]
) -> None:
    print("\n\n\n---HANDLE_MISSING_OBJECT CALLED---\n",
          f"  {file_identifier=}\n  {sha256=}\n  {metadata=}\n\n\n")


# %% colab={"base_uri": "https://localhost:8080/"} id="MoauJlFiSQW-" outputId="62bfda6c-21c9-407e-95f9-7e74a252a426"
# remove previously downloaded objects
shutil.rmtree(os.path.expanduser("~/.objaverse"), ignore_errors=True)

# redownload
oxl.download_objects(
    objects=missing_df,
    handle_found_object=handle_found_object,
    handle_modified_object=handle_modified_object,
    handle_missing_object=handle_missing_object  # <---------------
)


# %% [markdown] id="rlx6sE-WSgYD"
# Great! Notice how we get an error that the object could not be found and that our `handle_missing_object` callback is called!
#
# Finally, we'll also add a callback for `handle_new_object`, which will be called for every object that is in the repository, but not in the objects that we supplied for it to expect to download:

# %% id="nbMLHudBS3q3"
def handle_new_object(
    local_path: str,
    file_identifier: str,
    sha256: str,
    metadata: Dict[Hashable, Any]
) -> None:
    print("\n\n\n---HANDLE_NEW_OBJECT CALLED---\n",
          f"  {local_path=}\n  {file_identifier=}\n  {sha256=}\n  {metadata=}\n\n\n")


# %% colab={"base_uri": "https://localhost:8080/"} id="eXNk1_gSSXhI" outputId="f8c94d45-22b1-4d5f-ff85-6968a7fb6aca"
# remove previously downloaded objects
shutil.rmtree(os.path.expanduser("~/.objaverse"), ignore_errors=True)

# redownload
oxl.download_objects(
    objects=sampled_df,
    handle_found_object=handle_found_object,
    handle_modified_object=handle_modified_object,
    handle_missing_object=handle_missing_object,
    handle_new_object=handle_new_object,  # <---------------
)

# %% [markdown] id="R34bokNcTJpU"
# Notice that `handle_new_object` gets called a bunch of times!
#
# For even more objects, one may want to experiment with using the latest Git commits, instead of the ones used with Objaverse-XL, as it'll likely lead to more objects being available. Here, `handle_new_object` would be quite a useful callback!

# %% [markdown] id="LJCJ-cV1TmBy"
# ## Next Steps
#
# Take a look at the [Blender rendering code](https://github.com/allenai/objaverse-xl/tree/main/scripts/rendering) for rendering Objaverse-XL objects in Blender and extracting metadata from the objects!
