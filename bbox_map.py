import folium
from folium.plugins import Draw
from branca.element import Element


def create_map(out_fn: str) -> None:
    m = folium.Map(location=[47.5, 13.3], zoom_start=7)
    draw_layer = folium.FeatureGroup(name="drawn").add_to(m)

    draw = Draw(
        draw_options={
            "polyline": False,
            "polygon": False,
            "circle": False,
            "marker": False,
            "circlemarker": False,
            "rectangle": True
        },
        edit_options={"edit": False},
    )
    draw.add_to(m)

    clear_previous_js = f"""
    <script>
    document.addEventListener("DOMContentLoaded", function() {{
        // get map variable dynamically
        var map_obj = window.{m.get_name()};

        // global variable for drawn items
        window.drawnItems = null;

        map_obj.eachLayer(function(layer){{
            if(layer instanceof L.FeatureGroup){{
                window.drawnItems = layer;
            }}
        }});

        map_obj.on(L.Draw.Event.CREATED, function (e) {{
            window.drawnItems.clearLayers();     // remove old bbox
            window.drawnItems.addLayer(e.layer); // add new bbox
        }});
    }});
    </script>
    """
    m.get_root().html.add_child(Element(clear_previous_js))

    download_js = """
    <script>
    function downloadGeoJSON(){
        if (!window.drawnItems || window.drawnItems.getLayers().length === 0){
            alert("No bbox drawn yet!");
            return;
        }
        var data = window.drawnItems.toGeoJSON();
        var blob = new Blob([JSON.stringify(data)], {type: "application/json"});
        var url = URL.createObjectURL(blob);

        var a = document.createElement("a");
        a.href = url;
        a.download = `bbox_selection_${(new Date().toJSON().slice(0,19))}.geojson`
        a.click();
    }
    </script>

    <button onclick="downloadGeoJSON()" 
    style="position:absolute; top:10px; right:10px; z-index:1000;">
    Download bbox
    </button>
    """

    m.get_root().html.add_child(Element(download_js))
    m.save(out_fn)
    return None


if __name__ == '__main__':
    create_map(out_fn="files/bbox_draw_map.html")
