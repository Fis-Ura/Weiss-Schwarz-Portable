import os
import gzip
import shutil

def decompress_gzip_file(gzip_file_path, decompressed_file_path):
    with open(gzip_file_path, 'rb') as file:
        # Check for gzip magic bytes
        if file.read(2) == b'\x1f\x8b':
            file.seek(0)  # Reset file pointer to the beginning
            with gzip.open(file, 'rb') as gz_file:
                # Extract original file extension
                _, original_extension = os.path.splitext(gzip_file_path)
                decompressed_file_path = decompressed_file_path + "_decompressed" + original_extension
                with open(decompressed_file_path, 'wb') as dc_file:
                    shutil.copyfileobj(gz_file, dc_file)
                print(f"Decompressed: {gzip_file_path} -> {decompressed_file_path}")
        else:
            print(f"Not a gzip file: {gzip_file_path}")

def decompress_all_gzip_files(root_folder):
    for foldername, subfolders, filenames in os.walk(root_folder):
        for filename in filenames:
            file_path = os.path.join(foldername, filename)
            decompressed_file_path = os.path.join(foldername, filename)
            decompress_gzip_file(file_path, decompressed_file_path)

# Specify the root folder where you want to start decompression
root_folder = "FINAL"

# Call the function to decompress all gzip files recursively
decompress_all_gzip_files(root_folder)
