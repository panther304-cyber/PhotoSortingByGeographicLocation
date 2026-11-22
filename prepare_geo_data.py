"""
Download and prepare geographic boundary data for PhotoSorting.

Data sources:
  - Natural Earth 110m Admin 0: Countries (WGS-84)
  - GADM 4.1: China prefecture-level boundaries (WGS-84)
"""
import os
import sys
import zipfile
import shutil
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

# ── URLs ──────────────────────────────────────────────────────────
NE_URLS = [
    "https://naturalearth.s3.amazonaws.com/110m_cultural/ne_110m_admin_0_countries.zip",
    "https://github.com/nvkelso/natural-earth-vector/raw/master/110m_cultural/ne_110m_admin_0_countries.zip",
]

GADM_URL = (
    "https://geodata.ucdavis.edu/gadm/gadm4.1/gpkg/"
    "gadm41_CHN.gpkg"
)

def download_file(urls, dest: Path) -> tuple:
    """Download a file with progress reporting, trying multiple URLs."""
    import ssl
    # Create a lenient SSL context
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for url in (urls if isinstance(urls, list) else [urls]):
        print(f"Trying: {url}")
        print(f"  -> {dest}")
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) PhotoSorting/1.0'
            })
            with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
                total = int(response.headers.get('content-length', 0))
                downloaded = 0
                with open(dest, 'wb') as f:
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = min(100, downloaded * 100 // total)
                            sys.stdout.write(f"\r  {pct}% ({downloaded:,}/{total:,})")
                            sys.stdout.flush()
                print("\n  Done.")
                return url
        except Exception as e:
            print(f"\n  Failed: {e}")
            continue
    raise RuntimeError(f"All download attempts failed for {dest}")

def prepare_ne_countries() -> Path:
    """Download Natural Earth countries and extract shapefile."""
    dest_zip = DATA_DIR / "ne_110m_admin_0_countries.zip"
    extract_dir = DATA_DIR / "ne_110m"

    if not dest_zip.exists():
        download_file(NE_URLS, dest_zip)

    if not extract_dir.exists() or not list(extract_dir.glob("*.shp")):
        extract_dir.mkdir(exist_ok=True)
        print(f"Extracting: {dest_zip} -> {extract_dir}")
        with zipfile.ZipFile(dest_zip, 'r') as zf:
            zf.extractall(extract_dir)
        print("  Done.")

    # Find the .shp file
    shp_files = list(extract_dir.rglob("*.shp"))
    if not shp_files:
        raise FileNotFoundError(f"No .shp found in {extract_dir}")
    return shp_files[0]

def prepare_china_cities() -> Path:
    """Download GADM China data (already a GeoPackage)."""
    dest_gpkg = DATA_DIR / "gadm41_CHN.gpkg"

    if not dest_gpkg.exists():
        download_file(GADM_URL, dest_gpkg)
    else:
        print(f"Already exists: {dest_gpkg}")

    return dest_gpkg

def create_combined_gpkg(ne_shp: Path, china_gpkg: Path) -> Path:
    """Create a combined GeoPackage using DuckDB."""
    import duckdb

    output_gpkg = DATA_DIR / "photo_locations.gpkg"
    print(f"\nCreating combined GeoPackage: {output_gpkg}")

    conn = duckdb.connect()
    conn.execute("INSTALL spatial; LOAD spatial;")

    # 1. Import Natural Earth countries (select only needed columns)
    print("  Importing Natural Earth countries...")
    # First inspect column names
    cols = conn.execute(f"DESCRIBE SELECT * FROM ST_Read('{ne_shp.as_posix()}')").fetchall()
    geom_col = next(c[0] for c in cols if c[0].lower() in ('geom', 'geometry'))
    print(f"    Geometry column: {geom_col}")
    
    conn.execute(f"""
        CREATE TABLE countries AS
        SELECT
            NAME AS name_en,
            NAME AS name_zh,
            "{geom_col}" AS geometry
        FROM ST_Read('{ne_shp.as_posix()}')
        WHERE NAME IS NOT NULL
    """)
    count_countries = conn.execute("SELECT COUNT(*) FROM countries").fetchone()[0]
    print(f"    {count_countries} countries loaded")

    # 2. Import GADM China level-2 (prefecture/city) boundaries
    print("  Importing China city boundaries...")
    # Check available layers
    layers = conn.execute(f"SELECT * FROM ST_Drivers() WHERE short_name='GPKG'").fetchall()
    # Inspect GADM layers
    try:
        layer_info = conn.execute(f"""
            SELECT layer_name, geometry_column_name 
            FROM st_layers('{china_gpkg.as_posix()}')
        """).fetchall()
        print(f"    Available layers: {layer_info}")
    except:
        layer_info = None
    
    conn.execute(f"""
        CREATE TABLE china_cities AS
        SELECT
            NAME_2 AS city_name,
            NAME_1 AS province,
            geom AS geometry
        FROM ST_Read('{china_gpkg.as_posix()}', layer='ADM_ADM_2')
        WHERE NAME_2 IS NOT NULL AND NAME_2 != ''
    """)
    count_cities = conn.execute("SELECT COUNT(*) FROM china_cities").fetchone()[0]
    print(f"    {count_cities} cities loaded")

    # 3. Write to GeoPackage
    conn.execute(f"""
        COPY countries TO '{output_gpkg.as_posix()}' 
        (FORMAT GDAL, DRIVER 'GPKG', LAYER_NAME 'countries')
    """)
    conn.execute(f"""
        COPY china_cities TO '{output_gpkg.as_posix()}'
        (FORMAT GDAL, DRIVER 'GPKG', LAYER_NAME 'china_cities')
    """)

    conn.close()

    # Check file size
    size_mb = output_gpkg.stat().st_size / (1024 * 1024)
    print(f"  Done! Output size: {size_mb:.1f} MB")
    return output_gpkg

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("PhotoSorting - Geographic Data Preparation")
    print("=" * 60)

    ne_shp = prepare_ne_countries()
    print(f"NE Countries shapefile: {ne_shp}")

    china_gpkg = prepare_china_cities()
    print(f"China GADM GeoPackage: {china_gpkg}")

    combined_gpkg = create_combined_gpkg(ne_shp, china_gpkg)
    print(f"\nFinal GeoPackage ready: {combined_gpkg}")

    # Quick validation
    import duckdb
    conn = duckdb.connect()
    conn.execute("INSTALL spatial; LOAD spatial;")

    # Test a point in Shanghai
    result = conn.execute(f"""
        SELECT c.city_name, c.province
        FROM ST_Read('{combined_gpkg.as_posix()}', layer='china_cities') c
        WHERE ST_Contains(c.geom, ST_Point(121.4737, 31.2304))
        LIMIT 1
    """).fetchone()
    print(f"\nTest: GPS(121.47, 31.23) -> {result}")

    # Test a point in Tokyo
    result = conn.execute(f"""
        SELECT n.name_en
        FROM ST_Read('{combined_gpkg.as_posix()}', layer='countries') n
        WHERE ST_Contains(n.geom, ST_Point(139.6917, 35.6895))
        LIMIT 1
    """).fetchone()
    print(f"Test: GPS(139.69, 35.69) -> {result}")

    conn.close()
    print("\nAll done!")

if __name__ == "__main__":
    main()