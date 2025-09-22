import mimetypes
import re
import requests
from pathlib import Path
from urllib.parse import urlparse


# def download_image(url, output_dir: Path | str, preferred_name=None):
#     # TODO: refactor for better clarity
#     filename = preferred_name or Path(urlparse(url).path).name or "image"
#     response = requests.get(url)
#     mime_type = response.headers.get("content-type")
#     if mime_type:
#         mime_type = mime_type.split(";")[0].strip()
#         ext = mimetypes.guess_extension(mime_type)
#         if ext:
#             filename = Path(filename).with_suffix(ext).name
#     local_path = Path(output_dir) / filename  # absolute
#     if not local_path.exists():
#         local_path.parent.mkdir(exist_ok=True)
#         local_path.write_bytes(response.content)
#     return local_path


# def flatten_image_urls_to_paths(markdown_content, output_dir: Path | str, relative=False):
#     if isinstance(output_dir, str):
#         output_dir = Path(output_dir)

#     def replacer(match):
#         alt_text, url = match.groups()
#         path = download_image(url, output_dir, name=alt_text)
#         if relative:
#             path = path.relative_to(output_dir)
#         return f"![{alt_text}]({path})"

#     return re.sub(r"!\[([^\]]*)\]\((http[^)]+)\)", replacer, markdown_content)


def wrap_in_code_block(text: str, language: str = "") -> str:
    """
    Wraps the given text in a Markdown code block.

    Args:
        text: The text to wrap.
        language: The language for syntax highlighting.

    Returns:
        The wrapped text.
    """
    return f"```{language}\n{text}\n```"
