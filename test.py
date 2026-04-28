
import caelus

site_metadata = caelus.data.load_metadata("car")
latitude = site_metadata.get("latitude")
longitude = site_metadata.get("longitude")
data = caelus.data.load("car", 2014).loc["2014-01"]

sky_type = caelus.classify(data, latitude, longitude)

# sky_type_po = po.from_pandas(sky_type, include_index=True)
# caelus.filters.clean_spurious_sky_patches(sky_type_po)
