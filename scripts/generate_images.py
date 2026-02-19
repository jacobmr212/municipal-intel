"""
Generate og-image.png and favicon files for GovTech Diagnostic
Run: python3 scripts/generate_images.py
"""

from PIL import Image, ImageDraw, ImageFont
import os

# Create static directory if it doesn't exist
STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)

def create_og_image():
    """Create 1200x630 Open Graph image with actual logo"""
    print("Creating og-image.png...")

    # Create image with gradient-like blue background
    img = Image.new('RGB', (1200, 630), color='#1E3BC0')
    draw = ImageDraw.Draw(img)

    # Draw subtle circles for decoration
    draw.ellipse([700, -200, 1400, 500], fill='#162DA8', outline=None)
    draw.ellipse([-100, 300, 500, 900], fill='#162DA8', outline=None)

    # Load and composite the logo (use light version for dark background)
    logo_path = f"{STATIC_DIR}/govtech-logo-light-2x.png"
    try:
        logo = Image.open(logo_path)
        # Resize logo to appropriate size for og-image (width ~500px)
        logo_width = 500
        aspect_ratio = logo.height / logo.width
        logo_height = int(logo_width * aspect_ratio)
        logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)

        # Center the logo horizontally, position in upper-middle area
        logo_x = (1200 - logo_width) // 2
        logo_y = 140

        # Composite logo (handle transparency if present)
        if logo.mode == 'RGBA':
            img.paste(logo, (logo_x, logo_y), logo)
        else:
            img.paste(logo, (logo_x, logo_y))

        # Adjust y_offset for text below logo
        y_offset = logo_y + logo_height + 40

    except Exception as e:
        print(f"Warning: Could not load logo ({e}), falling back to text")
        # Fallback to original text-based design
        y_offset = 180
        try:
            title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 80)
        except:
            title_font = ImageFont.load_default()

        title = "GovTech Diagnostic"
        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        title_width = title_bbox[2] - title_bbox[0]
        draw.text(((1200 - title_width) / 2, y_offset), title, fill='white', font=title_font)
        y_offset += 110

    # Try to use a nice font for tagline, fall back to default
    try:
        subtitle_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 36)
        small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 26)
    except:
        subtitle_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    # Tagline
    subtitle = "Free ERP Readiness Assessment"
    subtitle_bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
    subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
    draw.text(((1200 - subtitle_width) / 2, y_offset), subtitle, fill='white', font=subtitle_font)

    # Second line
    y_offset += 50
    subtitle2 = "for Municipalities"
    subtitle2_bbox = draw.textbbox((0, 0), subtitle2, font=subtitle_font)
    subtitle2_width = subtitle2_bbox[2] - subtitle2_bbox[0]
    draw.text(((1200 - subtitle2_width) / 2, y_offset), subtitle2, fill='white', font=subtitle_font)

    # Domain
    y_offset += 70
    domain = "govtechdiagnostic.com"
    domain_bbox = draw.textbbox((0, 0), domain, font=small_font)
    domain_width = domain_bbox[2] - domain_bbox[0]

    # Draw rounded rectangle background for domain
    padding = 18
    box_x = (1200 - domain_width) / 2 - padding
    box_y = y_offset - 4
    box_width = domain_width + (padding * 2)
    box_height = 44
    draw.rounded_rectangle(
        [box_x, box_y, box_x + box_width, box_y + box_height],
        radius=10,
        fill='#2A4AD0'
    )

    draw.text(((1200 - domain_width) / 2, y_offset), domain, fill='white', font=small_font)

    # Save
    img.save(f"{STATIC_DIR}/og-image.png", 'PNG', optimize=True, quality=90)
    print(f"✓ Created {STATIC_DIR}/og-image.png (1200x630)")


def create_favicon():
    """Create 32x32 favicon.ico"""
    print("Creating favicon.ico...")

    # Create image
    img = Image.new('RGB', (32, 32), color='#1E3BC0')
    draw = ImageDraw.Draw(img)

    # Draw a simple "G" lettermark
    # Outer circle
    draw.ellipse([4, 4, 28, 28], fill=None, outline='white', width=3)

    # Gap on right side
    draw.rectangle([20, 13, 28, 19], fill='#1E3BC0')

    # Horizontal bar
    draw.rectangle([16, 14, 24, 18], fill='white')

    # Center dot
    draw.ellipse([14, 14, 18, 18], fill='white')

    # Save as ICO
    img.save(f"{STATIC_DIR}/favicon.ico", format='ICO', sizes=[(32, 32)])
    print(f"✓ Created {STATIC_DIR}/favicon.ico (32x32)")


def create_apple_touch_icon():
    """Create 180x180 Apple touch icon"""
    print("Creating apple-touch-icon.png...")

    # Create image with rounded corners
    size = 180
    img = Image.new('RGB', (size, size), color='#1E3BC0')
    draw = ImageDraw.Draw(img)

    # Draw a larger "G" lettermark
    center = size // 2

    # Outer circle
    draw.ellipse([30, 30, 150, 150], fill=None, outline='white', width=10)

    # Gap on right side
    draw.rectangle([105, 78, 150, 102], fill='#1E3BC0')

    # Horizontal bar
    draw.rectangle([90, 84, 120, 96], fill='white')

    # Center dot
    draw.ellipse([84, 84, 96, 96], fill='white')

    # Save
    img.save(f"{STATIC_DIR}/apple-touch-icon.png", 'PNG', optimize=True)
    print(f"✓ Created {STATIC_DIR}/apple-touch-icon.png (180x180)")


if __name__ == "__main__":
    print("Generating images for GovTech Diagnostic...\n")

    try:
        create_og_image()
        create_favicon()
        create_apple_touch_icon()
        print("\n✓ All images generated successfully!")
        print("\nNext steps:")
        print("1. Verify images look good: open static/og-image.png")
        print("2. Commit and push: git add static/*.png static/*.ico && git commit -m 'Add og-image and favicons' && git push")
        print("3. Test on govtechdiagnostic.com")
    except ImportError:
        print("\n❌ Error: Pillow (PIL) not installed")
        print("Install it with: pip3 install pillow")
        print("\nAlternatively, use the templates:")
        print("1. Open static/og-image-template.html in your browser")
        print("2. Take a screenshot and save as og-image.png")
        print("3. Convert static/favicon-template.svg to PNG using:")
        print("   - https://cloudconvert.com/svg-to-png")
        print("   - Or any SVG to PNG converter")
