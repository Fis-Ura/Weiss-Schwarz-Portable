import os
import struct
import sys
from io import BytesIO

def extract_BXI_chunks(bxi_file):
    output_directory = os.path.splitext(bxi_file)[0]
    os.makedirs(output_directory, exist_ok=True)
    
    with open(bxi_file, 'rb') as original_f:
        temp_f = BytesIO(original_f.read())
    
    temp_f.seek(0)
    header = temp_f.read(0x8)  # read 8 bytes header
    magic = struct.unpack_from('=4s', header, 0)[0]
    pair_count= struct.unpack_from('<I', header, 0x4)[0]
    
    print('header=', header.hex())
    print('magic=', magic.decode('utf-8'))
    print('pair_count=', hex(pair_count))
    
    structures = []
    temp_f.seek(0x8)
    for _ in range(pair_count * 2):
        structure = struct.unpack('<I', temp_f.read(4))[0]
        structures.append(structure)

    for (i, structure) in enumerate(structures):
        # Read the file offset and size from the table
        file_offset = structures[i]
        file_size = structures[i + 1] - file_offset if i + 1 < len(structures) else None
        print("File offset:", file_offset)

        # Extract the file data
        temp_f.seek(file_offset)
        file_data = temp_f.read(file_size)
        file_name = f"{i:03d}.bin"
        
        # Write the file data to the output directory
        output_file_path = os.path.join(output_directory, file_name)
        with open(output_file_path, 'wb') as output_file:
            output_file.write(file_data)


    print(f"All .bxi chunks extracted to {output_directory}.")
        
        
        
        
if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python bxi_tools.py <BXI_File>")
    else:
        bxi_file = sys.argv[1]
        extract_BXI_chunks(bxi_file)