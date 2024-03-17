# Weiss-Schwarz-Portable
An attempt to create a patch for Weiss Schwarz Portable(PSP).

# Hacker note 1 Main archive
__FINAL.BRP contain the main archive for the game
_FINAL_BRH has the header 

this is a work in progress but a script is available to open the archive and have access to the files, not all the file name have been found

```
struct Header
{
    u32 count;
    u32; // same as count
    u32 hash[count]; // name hash (used as sorting key)
    u32 offset[count]; // offset into BRP file (LBA-aligned)
    u32 size[count]; // size of data
    u32 hash2[count]; // content hash (including padding to next LBA-aligned offset)
};

// CRC algorithm
// Table initialization:
/*
var table = new uint[256];

for (uint i = 0; i < table.Length; i++)
{
    uint temp = i << 24;
    
    for (int j = 0; j < 8; j++)
    {
        if ((temp & 0x80000000) == 0)
            temp <<= 1;
        else
        {
            temp <<= 1;
            temp ^= 0x4C11DB7;
        }
    }

    table[i] = temp;
}
*/

// Hash computation:
/*
uint ComputeCrc(ReadOnlySpan<byte> buffer)
{
    uint hash = 0;

    foreach (byte b in buffer)
        hash = (hash << 8) ^ table[((hash >> 24) & 0xFF) ^ b];

    return ~hash;
}
*/

Header header @ 0;
```

An basic extraction script is found in tools under `Extractor.py`

provide the 2 mentioned file aboved and run the python script.

you can then run the gzip at the root of the folder with the above two file to decrompress all the files.


# Hacker note 2 Story files

Story event seems to be in a folder named LUA, they are compiled lua that can be opened with `unluac`

```
java -jar unluac.jar --disassemble --output out.lua EVENT0016.LUA
```

And they can be repacked with 

```
java -jar unluac.jar --assemble --output EVENT0016.LUA out.lua
```
the japanese character in the string in the decompiled lua will be escaped.

# Hacker note 3 compression

Lot of file have gzip compression, they are noted by their magic number 0x1f8b

# Hacker note 4 images
Most images are gims, gmo and some pngs in a gzip archive. Once decompressed you can access them with a tool like textER. 

1. when converting the `*.png` back `*.gim` the gimconv.exe tool settings for the one found in the normal game need to --pixel_order faster.

They both need to be brought back to 8bpp if they aren't to use this we use pngquant.exe with this setting --force --verbose 256 --ext .png

2. make sure that the footer with the conversion are not repacked into the file as this would make them bigger.
