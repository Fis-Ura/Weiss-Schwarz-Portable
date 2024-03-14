import os
import struct
import sys
from io import BytesIO

def extract_FRP_chunks(frp_file):
    output_directory = os.path.splitext(frp_file)[0]
    os.makedirs(output_directory, exist_ok=True)
    
    with open(frp_file, 'rb') as original_f:
        temp_f = BytesIO(original_f.read())
    
    temp_f.seek(0)
    header = temp_f.read(0x8)  # read 8 bytes header
    header_size = struct.unpack_from('<I', header, 0x0)[0]
    chunk_count = struct.unpack_from('<I', header, 0x4)[0]
    #chunk_name = struct.unpack_from('=20s', header, 0)[0]
    
    print('header=', header.hex())
    print('header size=', hex(header_size))
    #print('magic=', magic.decode('utf-8'))
    print('chunk_count=', hex(chunk_count))
    
    offset_structures = []
    temp_f.seek(0x8)
    for _ in range(chunk_count):
        structure = struct.unpack('<I', temp_f.read(4))[0]
        offset_structures.append(structure)
        print('offset =', hex(structure))
    
    size_structures = []
    temp_f.seek(0x8 + 0x4 * chunk_count)
    for _ in range(chunk_count):
        structure = struct.unpack('<I', temp_f.read(4))[0]
        size_structures.append(structure)
        print('size =', hex(structure))
        
        
    name_structures = []
    temp_f.seek(0x8 + (0x4 * (chunk_count * 2)))
    for _ in range(chunk_count):
        structure = struct.unpack_from('=32s', temp_f.read(0x20))[0]
        name_structures.append(structure)
        print('name=', structure.decode('utf-8'))

    for i in range(chunk_count):
        # Read the file offset and size from the table
        file_offset = offset_structures[i]
        file_size = size_structures[i]
        print("File offset:", file_offset)

        # Extract the file data
        temp_f.seek(file_offset)
        file_data = temp_f.read(file_size)
        file_name = name_structures[i].rstrip(b'\x00').decode('utf-8')
        
        print(file_name)
        # Write the file data to the output directory
        output_file_path = os.path.join(output_directory, file_name)
        with open(output_file_path, 'wb') as output_file:
            output_file.write(file_data)


    print(f"All .frp chunks extracted to {output_directory}.")
        
        
        
        
if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python frp_tools.py <FRP_File>")
    else:
        frp_file = sys.argv[1]
        extract_FRP_chunks(frp_file)