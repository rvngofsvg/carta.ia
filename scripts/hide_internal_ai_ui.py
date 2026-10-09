from pathlib import Path

# Client-facing app copy: no provider/model/cost internals.
app_path = Path('app.py')
app = app_path.read_text(encoding='utf-8')
old = 'st.caption(f"Alérgenos calculados por {data.get(\'_allergen_model\', MODELO_ALERGENOS)} y editables en Revisar.")'
new = 'st.caption("Alérgenos calculados automáticamente y editables en Revisar.")'
if old not in app:
    raise SystemExit('No se encontró caption técnico de alérgenos')
app = app.replace(old, new, 1)
app_path.write_text(app, encoding='utf-8')

# Qwen core logger must actually emit INFO records to private application logs.
core_path = Path('qwen_core.py')
core = core_path.read_text(encoding='utf-8')
needle = '_LOG = logging.getLogger("carta_ia.private_usage")\n'
if '_LOG.setLevel(logging.INFO)' not in core:
    if needle not in core:
        raise SystemExit('No se encontró logger privado Qwen')
    core = core.replace(needle, needle + '_LOG.setLevel(logging.INFO)\n', 1)
core_path.write_text(core, encoding='utf-8')

# AI design UI: remove cost/provider internals and keep usage/error detail in backend logs only.
design_path = Path('ai_design.py')
d = design_path.read_text(encoding='utf-8')
if 'import logging\n' not in d:
    d = d.replace('import json\n', 'import json\nimport logging\n', 1)

anchor = 'import streamlit as st\n\n\nALLERGEN_ORDER = ['
if '_PRIVATE_LOG = logging.getLogger("carta_ia.private_usage")' not in d:
    repl = ('import streamlit as st\n\n'
            '_PRIVATE_LOG = logging.getLogger("carta_ia.private_usage")\n'
            '_PRIVATE_LOG.setLevel(logging.INFO)\n\n\nALLERGEN_ORDER = [')
    if anchor not in d:
        raise SystemExit('No se encontró ancla de logger en ai_design.py')
    d = d.replace(anchor, repl, 1)

# Private image-generation usage records.
gen_old = '    response = _post_json(_dashscope_endpoint(), payload, api_key)\n    urls = _extract_image_urls(response)\n'
gen_new = ('    response = _post_json(_dashscope_endpoint(), payload, api_key)\n'
           '    _PRIVATE_LOG.info(json.dumps({"event":"CARTA_IA_QWEN_IMAGE_USAGE","model":model,"purpose":"design_proposals","images_requested":int(max(1, min(6, n))),"usage":response.get("usage") or {}}, ensure_ascii=False, sort_keys=True))\n'
           '    urls = _extract_image_urls(response)\n')
if '"purpose":"design_proposals"' not in d:
    if gen_old not in d:
        raise SystemExit('No se encontró llamada de propuestas Qwen Image')
    d = d.replace(gen_old, gen_new, 1)

ref_old = '    response = _post_json(_dashscope_endpoint(), payload, api_key)\n    urls = _extract_image_urls(response)\n'
ref_new = ('    response = _post_json(_dashscope_endpoint(), payload, api_key)\n'
           '    _PRIVATE_LOG.info(json.dumps({"event":"CARTA_IA_QWEN_IMAGE_USAGE","model":"qwen-image-3.0-pro","purpose":"design_refine","images_requested":1,"usage":response.get("usage") or {}}, ensure_ascii=False, sort_keys=True))\n'
           '    urls = _extract_image_urls(response)\n')
# Replace the second occurrence after refine function only.
if '"purpose":"design_refine"' not in d:
    refine_pos = d.index('def refine_qwen_background')
    before, after = d[:refine_pos], d[refine_pos:]
    if ref_old not in after:
        raise SystemExit('No se encontró llamada de refinado Qwen Image')
    after = after.replace(ref_old, ref_new, 1)
    d = before + after

replacements = {
    'st.markdown("### ✨ Diseño IA · Qwen Image")': 'st.markdown("### ✨ Diseño IA")',
    'st.warning("Añade DASHSCOPE_API_KEY en Streamlit Secrets para activar esta función.")': 'st.warning("El modo Diseño IA no está configurado. Contacta con el administrador.")',
    '    st.caption("Coste orientativo actual: 4 propuestas con Qwen Image 3.0 ≈ 0,09 €; refinado Pro ≈ 0,03 € a esta resolución. La tarifa puede cambiar.")\n\n': '',
    'with st.spinner("Qwen está creando cuatro direcciones visuales...")': 'with st.spinner("Creando cuatro propuestas visuales...")',
    'with st.spinner("Qwen Image Pro está refinando el concepto...")': 'with st.spinner("Refinando el concepto seleccionado...")',
    'st.image(final_bg, caption="Versión final refinada con Qwen Image 3.0 Pro", use_container_width=True)': 'st.image(final_bg, caption="Versión final refinada", use_container_width=True)',
    'st.info("Los textos, precios y alérgenos de estos PDF no los escribe Qwen: se colocan desde los datos reales de Carta IA encima del diseño generado.")': 'st.info("Los textos, precios y alérgenos se colocan desde los datos reales de Carta IA encima del diseño generado.")',
}
for old_text, new_text in replacements.items():
    if old_text in d:
        d = d.replace(old_text, new_text)

# Do not leak provider HTTP errors to the client in generation/refinement actions.
d = d.replace('''        except Exception as exc:
            st.error(str(exc))''', '''        except Exception as exc:
            _PRIVATE_LOG.exception("Fallo interno en Diseño IA: %s", exc)
            st.error("No se pudo generar el diseño. Inténtalo de nuevo en unos instantes.")''')

design_path.write_text(d, encoding='utf-8')

# Guardrails.
app_final = app_path.read_text(encoding='utf-8')
d_final = design_path.read_text(encoding='utf-8')
core_final = core_path.read_text(encoding='utf-8')
assert 'Alérgenos calculados por' not in app_final
assert 'Coste orientativo actual' not in d_final
assert 'DASHSCOPE_API_KEY en Streamlit Secrets' not in d_final
assert '_LOG.setLevel(logging.INFO)' in core_final
assert 'CARTA_IA_QWEN_IMAGE_USAGE' in d_final
print('Private AI UI cleanup applied')
