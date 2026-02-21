from PIL import Image
from PIL.ExifTags import TAGS
import pillow_heif

pillow_heif.register_heif_opener()

# Update this to the actual filename in your watch folder
image_path = r"G:\My Drive\Sps rowing\Erg pics\IMG_3168.HEIC"

img = Image.open(image_path)
print("Image format:", img.format)
print("Image mode:", img.mode)

exif = img.getexif()
print(f"\nTotal EXIF tags found: {len(exif)}")
for tag_id, value in exif.items():
    tag_name = TAGS.get(tag_id, tag_id)
    print(f"  {tag_name}: {value}")
