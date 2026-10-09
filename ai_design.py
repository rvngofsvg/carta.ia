import base64
import json
import logging
import os
import urllib.error
import urllib.request
from html import escape as html_escape
from io import BytesIO

import streamlit as st

_PRIVATE_LOG = logging.getLogger("carta_ia.private_usage")
_PRIVATE_LOG.setLevel(logging.INFO)


ALLERGEN_ORDER = [
    "gluten", "crustaceos", "huevos", "pescado", "cacahuetes", "soja", "lacteos",
    "frutos de cascara", "apio", "mostaza", "sesamo", "sulfitos", "altramuces", "moluscos",
]

ALLERGEN_LABELS = {
    "gluten": "Gluten", "crustaceos": "Crustáceos", "huevos": "Huevos", "pescado": "Pescado",
    "cacahuetes": "Cacahuetes", "soja": "Soja", "lacteos": "Lácteos",
    "frutos de cascara": "Frutos de cáscara", "apio": "Apio", "mostaza": "Mostaza",
    "sesamo": "Granos de sésamo", "sulfitos": "Dióxido de azufre y sulfitos",
    "altramuces": "Altramuces", "moluscos": "Moluscos",
}

STYLE_PRESETS = {
    "Elegante editorial": "high-end editorial restaurant menu, refined typography zones, restrained luxury, sophisticated print design",
    "Mediterráneo premium": "premium Mediterranean restaurant identity, warm natural stone, subtle sea and olive references, elegant handcrafted details",
    "Gastrobar moderno": "modern urban gastrobar, premium contemporary graphic design, bold but refined geometry, sophisticated restaurant branding",
    "Minimalista lujo": "luxury minimal restaurant design, generous negative space, subtle premium materials, timeless fine dining aesthetic",
    "Vintage artesanal": "artisan vintage restaurant print design, tasteful paper texture, engraved decorative accents, premium old-world hospitality",
    "Japonés contemporáneo": "contemporary Japanese fine dining design, restrained ink-inspired details, quiet luxury, elegant asymmetry",
    "Italiano sofisticado": "sophisticated Italian restaurant identity, editorial Milanese design, subtle heritage references, premium print finish",
    "Natural botánico": "premium botanical restaurant identity, elegant organic forms, natural materials, subtle foliage details, modern hospitality design",
    "Libre": "unique professional restaurant menu design",
}


def _secret(name, default=""):
    try:
        value = st.secrets[name]
        if value:
            return str(value).strip()
    except Exception:
        pass
    return str(os.getenv(name, default) or "").strip()


def _dashscope_key():
    return _secret("DASHSCOPE_API_KEY")


def _dashscope_endpoint():
    # Permite fijar un endpoint regional/workspace-specific en Secrets sin tocar código.
    configured = _secret("DASHSCOPE_IMAGE_ENDPOINT")
    if configured:
        return configured.rstrip("/")
    # Endpoint internacional heredado de Singapore; Alibaba indica que sigue operativo.
    return "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"


def _post_json(url, payload, api_key, timeout=240):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Alibaba Model Studio respondió HTTP {exc.code}: {detail[:900]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"No se pudo conectar con Alibaba Model Studio: {exc.reason}") from exc


def _download_bytes(url, timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": "CartaIA/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def _extract_image_urls(response):
    urls = []
    for choice in (response.get("output") or {}).get("choices") or []:
        content = ((choice.get("message") or {}).get("content") or [])
        for item in content:
            if isinstance(item, dict) and item.get("image"):
                urls.append(item["image"])
    # Compatibilidad con respuesta OpenAI-like si Alibaba cambia el wrapper.
    for item in response.get("data") or []:
        if isinstance(item, dict) and item.get("url"):
            urls.append(item["url"])
    return urls


def _menu_summary(data):
    categories = []
    total_dishes = 0
    for cat in data.get("categories", []):
        dishes = cat.get("dishes", [])
        total_dishes += len(dishes)
        categories.append(f"{cat.get('name', 'Categoría')} ({len(dishes)} platos)")
    return ", ".join(categories[:10]), total_dishes


def build_background_prompt(data, style_name, colors, brief):
    categories, total_dishes = _menu_summary(data)
    style = STYLE_PRESETS.get(style_name, STYLE_PRESETS["Libre"])
    restaurant = str(data.get("restaurant_name") or "Restaurante")
    return f"""
Create a unique A4 portrait background and visual system for a professional restaurant menu for '{restaurant}'.
Style: {style}.
Preferred palette: {colors or 'choose an elegant palette appropriate to the concept'}.
Restaurant structure: {categories or 'multiple menu sections'}, approximately {total_dishes} dishes.
Additional creative direction: {brief or 'none'}.

CRITICAL PRINT-LAYOUT RULES:
- This image is ONLY the visual background/template. Do NOT write menu items, prices, restaurant names, headings, letters, numbers, logos, allergen labels, QR codes or fake text.
- Leave generous clean readable zones in the center and across the page for deterministic text overlay later.
- Decorative elements must stay mainly near edges, corners, header/footer accents and section separators.
- Keep strong contrast and calm negative space; avoid busy food photography behind text zones.
- Professional hospitality art direction, premium print quality, balanced composition, no mockup perspective, no table scene, no hands, no paper photographed in an environment.
- Full-bleed flat A4 page design, portrait orientation, suitable for a real restaurant PDF.
""".strip()


def generate_qwen_backgrounds(data, style_name, colors="", brief="", n=4, model="qwen-image-3.0"):
    api_key = _dashscope_key()
    if not api_key:
        raise RuntimeError("Falta DASHSCOPE_API_KEY en los Secrets de Streamlit.")
    prompt = build_background_prompt(data, style_name, colors, brief)
    payload = {
        "model": model,
        "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
        "parameters": {
            "prompt_extend": True,
            "prompt_extend_mode": "agent",
            "enable_thinking": True,
            "n": int(max(1, min(6, n))),
            "size": "1024*1448",
            "negative_prompt": "readable text, letters, words, prices, numbers, logos, QR codes, watermark, clutter, low resolution, mockup perspective",
            "watermark": False,
        },
    }
    response = _post_json(_dashscope_endpoint(), payload, api_key)
    _PRIVATE_LOG.info(json.dumps({"event":"CARTA_IA_QWEN_IMAGE_USAGE","model":model,"purpose":"design_proposals","images_requested":int(max(1, min(6, n))),"usage":response.get("usage") or {}}, ensure_ascii=False, sort_keys=True))
    urls = _extract_image_urls(response)
    if not urls:
        raise RuntimeError("Alibaba no devolvió ninguna imagen. Revisa la región de la API key o el endpoint configurado.")
    return [_download_bytes(url) for url in urls]


def refine_qwen_background(image_bytes, data, style_name, colors="", brief=""):
    api_key = _dashscope_key()
    if not api_key:
        raise RuntimeError("Falta DASHSCOPE_API_KEY en los Secrets de Streamlit.")
    image_data = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
    prompt = build_background_prompt(data, style_name, colors, brief) + (
        "\nRefine this selected concept with Qwen Image Pro. Preserve the overall composition and safe text zones, "
        "but improve material realism, spacing, decorative consistency and premium print finish. Still add absolutely no text."
    )
    payload = {
        "model": "qwen-image-3.0-pro",
        "input": {"messages": [{"role": "user", "content": [{"image": image_data}, {"text": prompt}]}]},
        "parameters": {
            "prompt_extend": True,
            "prompt_extend_mode": "direct",
            "enable_thinking": True,
            "n": 1,
            "size": "1024*1448",
            "negative_prompt": "readable text, letters, words, prices, numbers, logos, QR codes, watermark, clutter, low resolution",
            "watermark": False,
        },
    }
    response = _post_json(_dashscope_endpoint(), payload, api_key)
    _PRIVATE_LOG.info(json.dumps({"event":"CARTA_IA_QWEN_IMAGE_USAGE","model":"qwen-image-3.0-pro","purpose":"design_refine","images_requested":1,"usage":response.get("usage") or {}}, ensure_ascii=False, sort_keys=True))
    urls = _extract_image_urls(response)
    if not urls:
        raise RuntimeError("Qwen Image Pro no devolvió una imagen refinada.")
    return _download_bytes(urls[0])


def _data_uri(image_bytes, mime="image/png"):
    return f"data:{mime};base64," + base64.b64encode(image_bytes).decode("ascii")


def _format_price(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if "€" in text:
        return text
    return text + " €"


def _dish_name(dish):
    number = str(dish.get("number") or "").strip()
    name = str(dish.get("name") or "").strip()
    return f"{number}. {name}" if number else name


def _icon_uri(path):
    if not path or not os.path.exists(path):
        return ""
    ext = os.path.splitext(path)[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    try:
        with open(path, "rb") as fh:
            return _data_uri(fh.read(), mime)
    except Exception:
        return ""


def _allergen_icons_html(allergens, icon_map, css_class="dish-icon"):
    order = {name: i for i, name in enumerate(ALLERGEN_ORDER)}
    normalized = sorted(set(allergens or []), key=lambda x: order.get(x, 999))
    parts = []
    for allergen in normalized:
        src = _icon_uri(icon_map.get(allergen))
        if src:
            parts.append(f'<img class="{css_class}" src="{src}" alt="{html_escape(ALLERGEN_LABELS.get(allergen, allergen))}">')
    return "".join(parts)


def _legend_html(icon_map):
    items = []
    for allergen in ALLERGEN_ORDER:
        src = _icon_uri(icon_map.get(allergen))
        icon = f'<img src="{src}" alt="">' if src else ""
        label = ALLERGEN_LABELS[allergen]
        if allergen == "sulfitos":
            label = "Dióxido de azufre<br>y sulfitos"
        items.append(f'<div class="legend-item">{icon}<span>{label}</span></div>')
    return (
        '<section class="legend"><div class="legend-law"><strong>'
        'Informamos de acuerdo con el Reglamento de la UE 1169/2011, que nuestros productos contienen o pueden contener los siguientes alérgenos.'
        '</strong></div><div class="legend-grid">' + "".join(items) + '</div></section>'
    )


def create_ai_menu_pdf(data, background_bytes, icon_map, with_allergens=True):
    try:
        from weasyprint import HTML
    except Exception as exc:
        raise RuntimeError("WeasyPrint no está disponible para generar el PDF visual.") from exc

    background = _data_uri(background_bytes)
    categories = []
    for cat in data.get("categories", []):
        rows = []
        for dish in cat.get("dishes", []):
            icons = _allergen_icons_html(dish.get("allergens", []), icon_map) if with_allergens else ""
            desc = html_escape(str(dish.get("description") or ""))
            desc_html = f'<div class="desc">{desc}</div>' if desc else ""
            rows.append(
                '<div class="dish">'
                f'<div class="line"><span class="name">{html_escape(_dish_name(dish))}</span>'
                '<span class="dots"></span>'
                f'<span class="price">{html_escape(_format_price(dish.get("price")))}</span>'
                f'<span class="icons">{icons}</span></div>{desc_html}</div>'
            )
        cat_text = html_escape(str(cat.get("category_text") or ""))
        cat_note = f'<div class="cat-note">{cat_text}</div>' if cat_text else ""
        categories.append(
            f'<section class="category"><h2>{html_escape(str(cat.get("name") or "Categoría"))}</h2>{cat_note}{"".join(rows)}</section>'
        )

    extra = html_escape(str(data.get("texto_extra") or ""))
    extra_html = f'<div class="extra">{extra}</div>' if extra else ""
    legend = _legend_html(icon_map) if with_allergens else ""
    title = html_escape(str(data.get("restaurant_name") or "MENÚ"))

    html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><style>
    @page {{ size:A4 portrait; margin:10mm; background-image:url('{background}'); background-size:cover; background-position:center; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Arial, sans-serif; color:#171717; }}
    .sheet {{ background:rgba(255,255,255,.88); border:1px solid rgba(30,30,30,.18); padding:8mm; border-radius:3mm; }}
    h1 {{ margin:0 0 6mm; text-align:center; font-family:Georgia,serif; font-size:26pt; letter-spacing:.8px; }}
    .category {{ break-inside:avoid; margin:0 0 5mm; }}
    h2 {{ margin:0 0 2.2mm; padding-bottom:1.2mm; border-bottom:1.2px solid rgba(30,30,30,.45); font-family:Georgia,serif; font-size:15pt; }}
    .cat-note {{ font-size:8.5pt; font-style:italic; margin-bottom:1.8mm; color:#444; }}
    .dish {{ margin:0 0 1.8mm; break-inside:avoid; }}
    .line {{ display:flex; align-items:center; gap:1.4mm; font-size:10.2pt; }}
    .name {{ font-weight:700; }}
    .dots {{ flex:1; min-width:8mm; border-bottom:1px dotted #777; height:0; }}
    .price {{ font-weight:700; white-space:nowrap; }}
    .icons {{ display:inline-flex; gap:.65mm; align-items:center; flex-shrink:0; }}
    .dish-icon {{ width:5.4mm; height:5.4mm; object-fit:contain; }}
    .desc {{ margin-top:.45mm; font-size:8.4pt; color:#4b4b4b; font-style:italic; }}
    .extra {{ margin:4mm 0; padding:2.5mm; border:1px solid rgba(30,30,30,.18); background:rgba(255,255,255,.55); font-size:8.5pt; }}
    .legend {{ margin-top:5mm; padding:2.2mm 2.5mm; border:1.75pt solid #333; background:rgba(255,255,255,.93); break-inside:avoid; }}
    .legend-law {{ text-align:center; font-size:7.5pt; margin-bottom:1.5mm; }}
    .legend-grid {{ display:grid; grid-template-columns:repeat(7,1fr); gap:1.2mm 1.5mm; }}
    .legend-item {{ text-align:center; font-size:6.5pt; font-weight:700; line-height:1.05; }}
    .legend-item img {{ display:block; width:9mm; height:9mm; object-fit:contain; margin:0 auto .6mm; }}
    </style></head><body><main class="sheet"><h1>{title}</h1>{''.join(categories)}{extra_html}{legend}</main></body></html>"""
    return HTML(string=html, base_url=os.getcwd()).write_pdf()


def render_ai_design_mode(data, icon_map):
    st.markdown("### ✨ Diseño IA")
    st.caption("La IA crea el fondo y la dirección artística. Carta IA coloca después platos, precios y alérgenos reales para no alterar datos.")

    if not _dashscope_key():
        st.warning("El modo Diseño IA no está configurado. Contacta con el administrador.")
        return

    c1, c2 = st.columns([1, 1])
    with c1:
        style_name = st.selectbox("Estilo visual", list(STYLE_PRESETS.keys()), key="ai_design_style")
    with c2:
        colors = st.text_input("Colores (opcional)", placeholder="Ej.: burdeos, crema y dorado", key="ai_design_colors")
    brief = st.text_area(
        "Indicaciones opcionales",
        placeholder="Ej.: restaurante de tapas premium en Barcelona, sobrio, sin fotografías de comida...",
        height=80,
        key="ai_design_brief",
    )

    if st.button("✨ GENERAR 4 PROPUESTAS", key="ai_design_generate", use_container_width=True):
        try:
            with st.spinner("Creando cuatro propuestas visuales..."):
                images = generate_qwen_backgrounds(data, style_name, colors, brief, n=4)
            st.session_state["ai_design_images"] = images
            st.session_state["ai_design_selected"] = 0
            st.session_state.pop("ai_design_final", None)
        except Exception as exc:
            _PRIVATE_LOG.exception("Fallo interno en Diseño IA: %s", exc)
            st.error("No se pudo generar el diseño. Inténtalo de nuevo en unos instantes.")

    images = st.session_state.get("ai_design_images") or []
    if not images:
        return

    cols = st.columns(len(images))
    for idx, (col, image_bytes) in enumerate(zip(cols, images)):
        with col:
            st.image(image_bytes, caption=f"Propuesta {idx + 1}", use_container_width=True)

    selected = st.radio(
        "Elegir propuesta",
        options=list(range(len(images))),
        format_func=lambda i: f"Propuesta {i + 1}",
        horizontal=True,
        key="ai_design_selected",
    )
    chosen = images[selected]

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "⬇️ DESCARGAR FONDO PNG",
            chosen,
            file_name="CartaIA_Fondo_Qwen.png",
            mime="image/png",
            use_container_width=True,
        )
    with c2:
        if st.button("✨ REFINAR ESTA PROPUESTA CON PRO", key="ai_design_refine", use_container_width=True):
            try:
                with st.spinner("Refinando el concepto seleccionado..."):
                    st.session_state["ai_design_final"] = refine_qwen_background(chosen, data, style_name, colors, brief)
            except Exception as exc:
                st.error(str(exc))

    final_bg = st.session_state.get("ai_design_final") or chosen
    if st.session_state.get("ai_design_final"):
        st.image(final_bg, caption="Versión final refinada", use_container_width=True)

    try:
        pdf_all = create_ai_menu_pdf(data, final_bg, icon_map, with_allergens=True)
        pdf_clean = create_ai_menu_pdf(data, final_bg, icon_map, with_allergens=False)
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "⬇️ PDF IA CON ALÉRGENOS",
                pdf_all,
                file_name="Carta_IA_Con_Alergenos.pdf",
                mime="application/pdf",
                key="ai_pdf_allergens",
                use_container_width=True,
            )
        with c2:
            st.download_button(
                "⬇️ PDF IA SIN ALÉRGENOS",
                pdf_clean,
                file_name="Carta_IA_Sin_Alergenos.pdf",
                mime="application/pdf",
                key="ai_pdf_clean",
                use_container_width=True,
            )
        st.info("Los textos, precios y alérgenos se colocan desde los datos reales de Carta IA encima del diseño generado.")
    except Exception as exc:
        st.error(f"No se pudo construir el PDF final: {exc}")
