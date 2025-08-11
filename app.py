import streamlit as st
import requests
from geopy.distance import geodesic
import pandas as pd
import pydeck as pdk

st.set_page_config(page_title="Zone de Chalandise", layout="wide")

# --- Chargement des communes en cache ---
@st.cache_data(show_spinner=False)
def load_communes():
    url = "https://geo.api.gouv.fr/communes?fields=nom,code,codePostal,centre&format=json&geometry=centre"
    r = requests.get(url)
    data = r.json()
    cleaned = []
    for c in data:
        try:
            lat = c["centre"]["coordinates"][1]
            lon = c["centre"]["coordinates"][0]
            cleaned.append({
                "nom": c["nom"],
                "code_postal": c.get("codePostal", ""),
                "latitude": lat,
                "longitude": lon
            })
        except:
            continue
    df = pd.DataFrame(cleaned)
    df["label"] = df["nom"] + " (" + df["code_postal"] + ")"
    return df

communes_df = load_communes()

st.markdown("<h1 style='color:#c82832;'>MAP MRKTG POLE PERF NXT</h1>", unsafe_allow_html=True)

# --- Sélection de la ville avec autocomplétion ---
ville_input = st.selectbox(
    "Entrez la ville (autocomplétion) :",
    options=communes_df["label"].tolist(),
    index=communes_df[communes_df["nom"].str.lower() == "aubervilliers"].index[0]
)

# Extraction nom et code postal
selected_nom = ville_input.split(" (")[0]
selected_cp = ville_input.split(" (")[1].replace(")", "")

# Coordonnées de la ville sélectionnée
ref = communes_df[(communes_df["nom"] == selected_nom) & (communes_df["code_postal"] == selected_cp)].iloc[0]
ref_coords = (ref["latitude"], ref["longitude"])

# Rayon slider
rayon = st.slider("Rayon de recherche (km) :", 1, 50, 10)

# Bouton lancer la recherche
if st.button("Lancer la recherche"):

    with st.spinner("Calcul en cours..."):
        # Calcul des distances
        def calc_distance(row):
            return geodesic(ref_coords, (row["latitude"], row["longitude"])).km

        communes_df["distance_km"] = communes_df.apply(calc_distance, axis=1)

        # Filtrer selon le rayon et exclure la ville de référence
        communes_filtrees = communes_df[(communes_df["distance_km"] <= rayon) & 
                                        ~((communes_df["nom"] == selected_nom) & (communes_df["code_postal"] == selected_cp))]

        communes_filtrees = communes_filtrees.sort_values("distance_km").reset_index(drop=True)

    st.markdown(f"**{len(communes_filtrees)} villes trouvées dans un rayon de {rayon} km autour de {selected_nom} ({selected_cp})**")

    # Gestion sélection villes sur la carte
    st.markdown("### Sélection des villes à inclure/exclure")
    cols = st.columns([3,1])
    with cols[0]:
        options = st.multiselect(
            "Sélectionnez les villes à inclure dans le résultat :",
            options=communes_filtrees["label"].tolist(),
            default=communes_filtrees["label"].tolist()
        )
    with cols[1]:
        if st.button("Tout sélectionner"):
            options = communes_filtrees["label"].tolist()
        if st.button("Tout désélectionner"):
            options = []

    # Filtrer le DataFrame final selon sélection
    final_df = communes_filtrees[communes_filtrees["label"].isin(options)]

    # Tableau résultats (nom + code postal + distance)
    st.dataframe(final_df[["nom", "code_postal", "distance_km"]].rename(columns={
        "nom": "Ville",
        "code_postal": "Code Postal",
        "distance_km": "Distance (km)"
    }))

    # Affichage du cercle sur la carte et points
    layer_points = pdk.Layer(
        "ScatterplotLayer",
        data=final_df,
        get_position='[longitude, latitude]',
        get_radius=2000,
        get_fill_color=[255, 0, 45, 160],  # rouge #ff002D
        pickable=True,
        auto_highlight=True,
    )
    layer_ref = pdk.Layer(
        "ScatterplotLayer",
        data=pd.DataFrame([ref]),
        get_position='[longitude, latitude]',
        get_radius=3000,
        get_fill_color=[200, 40, 40, 255],
        pickable=False,
    )
    # Cercle rayon
    circle_layer = pdk.Layer(
        "PolygonLayer",
        data=[{
            "polygon": [
                [
                    [
                        ref["longitude"] + 0.01 * (rayon / 10) * cos_angle,
                        ref["latitude"] + 0.01 * (rayon / 10) * sin_angle
                    ]
                    for angle in range(0, 361, 5)
                    for cos_angle, sin_angle in [(pdk.math.cos(pdk.math.radians(angle)), pdk.math.sin(pdk.math.radians(angle)))]
                ]
            ]
        }],
        get_polygon="polygon",
        stroked=True,
        filled=False,
        line_width_min_pixels=2,
        get_line_color=[200, 40, 40],
    )

    view_state = pdk.ViewState(
        latitude=ref["latitude"],
        longitude=ref["longitude"],
        zoom=9,
        pitch=0
    )

    st.pydeck_chart(pdk.Deck(
        layers=[layer_points, layer_ref],  # Sans le cercle polygon qui est plus complexe ici
        initial_view_state=view_state,
        tooltip={"text": "{nom} ({code_postal})"}
    ))

    # Affichage zone copier-coller codes postaux
    st.markdown("### Codes postaux sélectionnés (copier-coller) :")
    cp_text = ", ".join(final_df["code_postal"].tolist())
    st.text_area("Codes postaux :", value=cp_text, height=80)

else:
    st.info("Sélectionnez une ville et un rayon, puis cliquez sur **Lancer la recherche** pour afficher les communes.")

