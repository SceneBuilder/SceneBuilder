
import pandas as pd
import requests
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO
import csv

# The data provided by the user.
data_path = "./experiments/catalog-export-20250806172208.csv"

def download_image(url, filename, output_dir):
    """Downloads an image from a URL and saves it to a directory."""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        # Sanitize filename
        sanitized_filename = "".join([c for c in filename if c.isalpha() or c.isdigit() or c.isspace() or c in ('.', '-', '_')]).rstrip()
        filepath = os.path.join(output_dir, sanitized_filename)
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return f"Downloaded {sanitized_filename}"
    except requests.exceptions.RequestException as e:
        return f"Failed to download {url}: {e}"

def main():
    """
    Parses the CSV data, extracts image URLs, and downloads them in parallel.
    """
    # Create a directory to save the images
    output_dir = "floor_plan_images"
    os.makedirs(output_dir, exist_ok=True)
    print(f"Saving images to {output_dir}/")

    # Read data
    df = pd.read_csv(data_path)

    # Find all digital object columns
    digital_object_cols = [col for col in df.columns if col.startswith('digitalObjects.')]
    # group them by the index
    digital_object_indices = sorted(list(set([int(c.split('.')[1]) for c in digital_object_cols if c.split('.')[1].isdigit()])))

    urls_to_download = []
    for index, row in df.iterrows():
        for i in digital_object_indices:
            obj_type_col = f'digitalObjects.{i}.objectType'
            obj_url_col = f'digitalObjects.{i}.objectUrl'
            obj_filename_col = f'digitalObjects.{i}.objectFilename'

            if obj_type_col in df.columns and obj_url_col in df.columns and obj_filename_col in df.columns:
                obj_type = row[obj_type_col]
                url = row[obj_url_col]
                filename = row[obj_filename_col]

                if isinstance(obj_type, str) and 'Image' in obj_type and pd.notna(url) and pd.notna(filename) and url:
                    urls_to_download.append((url, filename))

    print(f"Found {len(urls_to_download)} images to download.")

    # Use ThreadPoolExecutor for parallel downloads
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(download_image, url, filename, output_dir) for url, filename in urls_to_download]
        for future in as_completed(futures):
            print(future.result())

    print("Download process finished.")

if __name__ == "__main__":
    main()
