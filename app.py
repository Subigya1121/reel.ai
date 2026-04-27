import streamlit as st
import anthropic
import requests
import os
import tempfile
import shutil
import json
import textwrap
import io
import time
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips

# ── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="REEL.AI — AI Video Generator",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=Space+Grotesk:wght@400;500;600&display=swap');

  html, body, [class*="css"] { font-family: 'Space Grotesk', sans-serif; }

  .main { background: #030308; }
  .block-container { padding-top: 2rem; max-width: 900px; }

  h1,h2,h3 { font-family: 'Syne', sans-serif !important; }

  .hero-title {
    font-family: 'Syne', sans-serif;
    font-size: 2.8rem;
    font-weight: 800;
    background: linear-gradient(135deg, #6ee7f7, #818cf8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    text-align: center;
    margin-bottom: 0;
  }
  .hero-sub {
    text-align: center;
    color: #64748b;
    font-size: 1rem;
    margin-top: 0.3rem;
  }
  .badge {
    display: inline-block;
    background: rgba(247,37,133,0.2);
    border: 1px solid rgba(247,37,133,0.5);
    border-radius: 6px;
    padding: 2px 10px;
    font-size: 0.7rem;
    color: #f72585;
    font-weight: 700;
    letter-spacing: 1px;
    margin-left: 8px;
    vertical-align: middle;
  }
  .scene-box {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(110,231,247,0.15);
    border-radius: 12px;
    padding: 14px 18px;
    margin-bottom: 10px;
  }
  .scene-title { color: #6ee7f7; font-weight: 700; font-size: 0.9rem; }
  .scene-visual { color: #94a3b8; font-size: 0.82rem; margin-top: 3px; }
  .hashtag-pill {
    display: inline-block;
    background: rgba(110,231,247,0.1);
    border: 1px solid rgba(110,231,247,0.3);
    border-radius: 999px;
    padding: 3px 12px;
    font-size: 0.78rem;
    color: #6ee7f7;
    margin: 3px;
  }
  .info-box {
    background: rgba(110,231,247,0.05);
    border: 1px solid rgba(110,231,247,0.2);
    border-radius: 10px;
    padding: 12px 16px;
    font-size: 0.85rem;
    color: #94a3b8;
  }
  div[data-testid="stButton"] > button {
    background: linear-gradient(135deg, #6ee7f7, #818cf8) !important;
    color: #000 !important;
    font-family: 'Syne', sans-serif !important;
    font-weight: 700 !important;
    border: none !important;
    border-radius: 12px !important;
    font-size: 1rem !important;
    padding: 0.6rem 2rem !important;
    box-shadow: 0 0 20px rgba(110,231,247,0.3) !important;
    transition: all 0.3s !important;
  }
  div[data-testid="stButton"] > button:hover {
    box-shadow: 0 0 35px rgba(110,231,247,0.6) !important;
    transform: translateY(-2px) !important;
  }
  .stTextInput > div > div > input,
  .stTextArea > div > div > textarea {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
    font-family: 'Space Grotesk', sans-serif !important;
  }
  .stSelectbox > div > div {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
  }
  section[data-testid="stSidebar"] {
    background: #0c0c18 !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
  }
  .stProgress > div > div {
    background: linear-gradient(90deg, #6ee7f7, #818cf8) !important;
    border-radius: 4px !important;
  }
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
TEMPLATE_COLORS = {
    "Cinematic":   (15, 12, 41),
    "Motivational":(140, 30, 10),
    "Educational": (0, 60, 100),
    "News":        (20, 25, 45),
    "Aesthetic":   (180, 120, 130),
}

LANG_CODES = {
    "English 🇬🇧": "en",
    "Nepali 🇳🇵": "ne",
    "Both English + Nepali 🌏": "en",
}

# ── Utility helpers ────────────────────────────────────────────────────────────
def get_font(size=28):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()

def clean_json(text):
    text = text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()

# ── API helpers ───────────────────────────────────────────────────────────────
def call_claude(api_key, prompt, system="You are an expert viral content creator.", max_tokens=1500):
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text

def fetch_pexels_image(query, api_key, orientation="portrait"):
    if not api_key or not api_key.strip():
        return None
    try:
        headers = {"Authorization": api_key.strip()}
        params = {"query": query, "per_page": 3, "orientation": orientation}
        r = requests.get("https://api.pexels.com/v1/search", headers=headers, params=params, timeout=12)
        r.raise_for_status()
        photos = r.json().get("photos", [])
        if photos:
            url = photos[0]["src"]["large"]
            img_resp = requests.get(url, timeout=20)
            return Image.open(io.BytesIO(img_resp.content))
    except Exception:
        return None
    return None

# ── Image creation ─────────────────────────────────────────────────────────────
def create_scene_image(bg_img, subtitle_text, width, height, template_name):
    base_color = TEMPLATE_COLORS.get(template_name, (15, 12, 41))

    if bg_img:
        img = bg_img.convert("RGB")
        # smart crop to fill target size
        img_w, img_h = img.size
        target_ratio = width / height
        src_ratio = img_w / img_h
        if src_ratio > target_ratio:
            new_w = int(img_h * target_ratio)
            left = (img_w - new_w) // 2
            img = img.crop((left, 0, left + new_w, img_h))
        else:
            new_h = int(img_w / target_ratio)
            top = (img_h - new_h) // 2
            img = img.crop((0, top, img_w, top + new_h))
        img = img.resize((width, height), Image.LANCZOS)

        # darken overlay for readability
        dark = Image.new("RGBA", (width, height), (0, 0, 0, 140))
        img = Image.alpha_composite(img.convert("RGBA"), dark).convert("RGB")
    else:
        # Gradient fallback
        img = Image.new("RGB", (width, height))
        draw_bg = ImageDraw.Draw(img)
        r, g, b = base_color
        for y in range(height):
            ratio = y / height
            nr = int(r + (255 - r) * ratio * 0.08)
            ng = int(g + (255 - g) * ratio * 0.08)
            nb = int(b + (255 - b) * ratio * 0.08)
            draw_bg.line([(0, y), (width, y)], fill=(nr, ng, nb))

    draw = ImageDraw.Draw(img)

    # Font sizing based on resolution
    font_size = max(20, width // 18)
    font = get_font(font_size)

    # Word-wrap subtitle
    chars_per_line = max(10, width // (font_size // 2 + 2))
    lines = textwrap.wrap(subtitle_text or "", width=chars_per_line)
    if not lines:
        return img

    line_h = font_size + 10
    box_h = len(lines) * line_h + 28
    box_y = height - box_h - 24

    # Semi-transparent subtitle backdrop
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    ov_draw.rounded_rectangle([16, box_y, width - 16, height - 16], radius=10, fill=(0, 0, 0, 185))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    y = box_y + 14
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
        except Exception:
            text_w = len(line) * (font_size // 2)
        x = (width - text_w) // 2
        # drop shadow
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0))
        # white text
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += line_h

    return img

# ── TTS ───────────────────────────────────────────────────────────────────────
def generate_voice(text, lang_code="en"):
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    try:
        tts = gTTS(text=text.strip(), lang=lang_code, slow=False)
        tts.save(tmp.name)
        return tmp.name
    except Exception as e:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
        raise RuntimeError(f"TTS failed: {e}")

# ── Video Assembly ─────────────────────────────────────────────────────────────
def assemble_video(processed_scenes, work_dir, fps=24):
    clips = []
    try:
        for i, scene in enumerate(processed_scenes):
            img_path = os.path.join(work_dir, f"frame_{i}.jpg")
            scene["image"].save(img_path, quality=88)

            audio_path = scene.get("audio_path")
            if audio_path and os.path.exists(audio_path):
                audio = AudioFileClip(audio_path)
                duration = audio.duration + 0.4
                clip = ImageClip(img_path).set_duration(duration).set_audio(audio)
            else:
                clip = ImageClip(img_path).set_duration(scene.get("duration", 5))

            # Fade in/out
            clip = clip.crossfadein(0.4).crossfadeout(0.4)
            clips.append(clip)

        if not clips:
            raise ValueError("No clips to assemble.")

        final = concatenate_videoclips(clips, method="compose", padding=-0.3)
        out_path = os.path.join(work_dir, "reel_ai_video.mp4")
        final.write_videofile(
            out_path,
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            verbose=False,
            logger=None,
        )
        final.close()
        for c in clips:
            c.close()
        return out_path
    except Exception as e:
        for c in clips:
            try:
                c.close()
            except Exception:
                pass
        raise e

# ── Main generation pipeline ──────────────────────────────────────────────────
def run_pipeline(anthropic_key, pexels_key, topic, format_type, tone, language, template):
    work_dir = tempfile.mkdtemp(prefix="reel_ai_")
    audio_files = []

    try:
        pb = st.progress(0)
        status = st.empty()
        is_short = format_type == "Short-form (Reels/TikTok)"
        width, height = (540, 960) if is_short else (960, 540)
        lang_code = LANG_CODES.get(language, "en")
        orient = "portrait" if is_short else "landscape"

        # ── STEP 1: Script ────────────────────────────────────────────────────
        status.markdown("✍️ **Writing your viral script...**")
        lang_note = ""
        if "Nepali" in language and "English" in language:
            lang_note = "Write in English and add a Nepali translation (नेपाली) below each paragraph."
        elif "Nepali" in language:
            lang_note = "Write entirely in Nepali (नेपाली भाषामा लेख्नुहोस्)."

        script = call_claude(
            anthropic_key,
            f"""Write a {"60-90 second TikTok/Reels" if is_short else "3-5 minute YouTube"} script about: "{topic}"
Tone: {tone} | Style: {template}
{lang_note}

Structure:
[HOOK] Strong 1-2 sentence opener
[MAIN CONTENT] 3-4 engaging paragraphs
[CTA] Clear call to action

Be punchy, conversational, and perfectly paced.""",
            system="You are an elite viral content creator with 10M+ follower clients. Write gripping scripts.",
            max_tokens=1200,
        )
        st.session_state["script"] = script
        pb.progress(18)

        # ── STEP 2: Scenes JSON ───────────────────────────────────────────────
        status.markdown("🎬 **Planning your scenes...**")
        scenes_raw = call_claude(
            anthropic_key,
            f"""Break this script into exactly 5 scenes for a video. Return ONLY a valid JSON array:
[
  {{
    "scene": "Scene Name",
    "visual": "3-word image search term for Pexels",
    "scene_text": "The narration text for this scene (1-3 sentences from the script)",
    "duration": 8,
    "emoji": "🎬"
  }}
]

Script:
{script}""",
            system="Return ONLY valid JSON. No markdown, no explanation, no extra text.",
            max_tokens=800,
        )
        try:
            scenes_data = json.loads(clean_json(scenes_raw))
            if not isinstance(scenes_data, list):
                raise ValueError
        except Exception:
            scenes_data = [
                {"scene": "Opening Hook", "visual": topic + " dramatic", "scene_text": "Get ready for something incredible.", "duration": 6, "emoji": "⚡"},
                {"scene": "Background", "visual": topic + " overview", "scene_text": "Here's what you need to know.", "duration": 8, "emoji": "🎬"},
                {"scene": "Key Facts", "visual": topic + " details", "scene_text": "The most important facts revealed.", "duration": 10, "emoji": "💡"},
                {"scene": "Deep Dive", "visual": topic + " closeup", "scene_text": "Let's dig deeper into this topic.", "duration": 8, "emoji": "🔍"},
                {"scene": "Call to Action", "visual": "follow subscribe social", "scene_text": "Like and follow for more content!", "duration": 5, "emoji": "🔔"},
            ]
        st.session_state["scenes_data"] = scenes_data
        pb.progress(30)

        # ── STEP 3: Meta (title + hashtags) ──────────────────────────────────
        status.markdown("🏷️ **Generating title & hashtags...**")
        meta_raw = call_claude(
            anthropic_key,
            f"""For a {tone} {"Reels/TikTok" if is_short else "YouTube"} video about "{topic}" return ONLY JSON:
{{"title":"Viral video title max 70 chars","hashtags":["#tag1","#tag2","#tag3","#tag4","#tag5","#tag6","#tag7","#tag8","#tag9","#tag10"]}}""",
            system="Return ONLY valid JSON. No markdown.",
            max_tokens=300,
        )
        try:
            meta = json.loads(clean_json(meta_raw))
        except Exception:
            meta = {"title": f"The Truth About {topic} 🔥", "hashtags": ["#viral", "#trending", "#reels", "#youtube", f"#{topic.replace(' ','').lower()}"]}
        st.session_state["meta"] = meta
        pb.progress(38)

        # ── STEP 4: Process each scene ────────────────────────────────────────
        processed = []
        total_scenes = min(len(scenes_data), 5)

        for i, scene in enumerate(scenes_data[:5]):
            status.markdown(f"🖼️ **Processing scene {i+1} of {total_scenes} — {scene.get('scene','...')}**")

            # Fetch background image
            visual_query = scene.get("visual", topic)
            bg = fetch_pexels_image(visual_query, pexels_key, orient)

            # Create scene image with subtitle overlay
            narration = scene.get("scene_text", scene.get("scene", ""))
            img = create_scene_image(bg, narration, width, height, template)

            # Generate TTS audio
            audio_path = None
            try:
                if narration.strip():
                    audio_path = generate_voice(narration, lang_code)
                    audio_files.append(audio_path)
            except Exception:
                pass

            processed.append({
                "image": img,
                "audio_path": audio_path,
                "duration": scene.get("duration", 7),
                "scene_name": scene.get("scene", f"Scene {i+1}"),
                "visual": scene.get("visual", ""),
                "emoji": scene.get("emoji", "🎬"),
                "narration": narration,
            })
            pb.progress(38 + int(42 * (i + 1) / total_scenes))

        # ── STEP 5: Assemble video ────────────────────────────────────────────
        status.markdown("🎞️ **Assembling your video — almost done!**")
        video_path = assemble_video(processed, work_dir, fps=24)
        pb.progress(96)

        # Read video into memory
        with open(video_path, "rb") as f:
            video_bytes = f.read()

        pb.progress(100)
        status.markdown("✅ **Your video is ready!**")
        time.sleep(0.5)
        status.empty()
        pb.empty()

        return video_bytes, processed, meta

    finally:
        # Cleanup temp audio files
        for af in audio_files:
            try:
                os.unlink(af)
            except Exception:
                pass
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass

# ── Session state init ────────────────────────────────────────────────────────
for key in ["video_bytes", "script", "scenes_data", "meta", "processed_scenes"]:
    if key not in st.session_state:
        st.session_state[key] = None

# ── Load keys from Streamlit Secrets ─────────────────────────────────────────
anthropic_key = st.secrets.get("ANTHROPIC_KEY", "")
pexels_key    = st.secrets.get("PEXELS_KEY", "")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎬 REEL.AI")
    st.markdown("<div class='info-box'>Powered by Claude AI · Free to use · No sign-up needed</div>", unsafe_allow_html=True)
    st.markdown("")
    st.markdown("### ⚡ Tech Stack")
    st.markdown("""
- 🧠 Claude Haiku (Script AI)
- 🗣️ gTTS (English & Nepali Voice)
- 🖼️ Pexels (Stock Photo Backgrounds)
- 🎞️ MoviePy + FFmpeg (Video Assembly)
- 🐍 Python + Streamlit (Hosting)
    """)
    st.markdown("---")
    st.markdown("### 🇳🇵 Built for Nepal & Creators Worldwide")
    st.markdown("Made with ❤️ using Claude AI")

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<p class="hero-title">🎬 REEL.AI <span class="badge">BETA</span></p>', unsafe_allow_html=True)
st.markdown('<p class="hero-sub">Topic → Full AI Video in One Click · Nepali & English · Built for Creators 🇳🇵</p>', unsafe_allow_html=True)
st.markdown("---")

# ── Main Form ─────────────────────────────────────────────────────────────────
col1, col2 = st.columns([2, 1])

with col1:
    topic = st.text_area(
        "💡 Your Video Topic",
        placeholder="e.g. Mount Everest Climbing Facts, Python Tutorial for Beginners, Morning Routine for Success...",
        height=100,
    )

with col2:
    format_type = st.selectbox("📱 Format", [
        "Short-form (Reels/TikTok)",
        "Long-form (YouTube)",
    ])
    tone = st.selectbox("🎭 Tone", ["Educational", "Motivational", "Funny", "News", "Storytelling"])

col3, col4 = st.columns(2)
with col3:
    language = st.selectbox("🌍 Language", [
        "English 🇬🇧",
        "Nepali 🇳🇵",
        "Both English + Nepali 🌏",
    ])
with col4:
    template = st.selectbox("🎨 Visual Template", [
        "Cinematic", "Motivational", "Educational", "News", "Aesthetic"
    ])

st.markdown("")
generate_btn = st.button("🚀 Generate My Video", use_container_width=True)

# ── Generate ──────────────────────────────────────────────────────────────────
if generate_btn:
    if not anthropic_key:
        st.error("⚠️ App not configured yet. Please contact the site owner.")
    elif not topic.strip():
        st.warning("⚠️ Please enter a topic for your video.")
    else:
        try:
            video_bytes, processed, meta = run_pipeline(
                anthropic_key, pexels_key, topic,
                format_type, tone, language, template
            )
            st.session_state["video_bytes"] = video_bytes
            st.session_state["processed_scenes"] = processed
        except anthropic.AuthenticationError:
            st.error("❌ Invalid Anthropic API key. Please check and try again.")
        except Exception as e:
            st.error(f"❌ Something went wrong: {str(e)}")
            st.info("💡 Try again — gTTS occasionally has network hiccups.")

# ── Results ───────────────────────────────────────────────────────────────────
if st.session_state["video_bytes"]:
    st.markdown("---")
    st.markdown("## 🎉 Your Video is Ready!")

    # Video player
    st.video(st.session_state["video_bytes"])

    # Download button
    fname = f"reel_ai_{topic[:30].replace(' ','_') if topic else 'video'}.mp4"
    st.download_button(
        label="⬇️ Download MP4",
        data=st.session_state["video_bytes"],
        file_name=fname,
        mime="video/mp4",
        use_container_width=True,
    )

    # Title & Hashtags
    if st.session_state.get("meta"):
        meta = st.session_state["meta"]
        st.markdown(f"### 📌 {meta.get('title','')}")
        hashtags = meta.get("hashtags", [])
        if hashtags:
            pills = " ".join([f'<span class="hashtag-pill">{h}</span>' for h in hashtags])
            st.markdown(pills, unsafe_allow_html=True)

    # Scene storyboard
    if st.session_state.get("processed_scenes"):
        st.markdown("### 🎞️ Scene Storyboard")
        for s in st.session_state["processed_scenes"]:
            st.markdown(f"""
<div class="scene-box">
  <span style="font-size:1.4rem">{s['emoji']}</span>&nbsp;
  <span class="scene-title">{s['scene_name']}</span>&nbsp;
  <span style="color:#475569;font-size:0.75rem">· {s['duration']}s · {'🎙️ Audio' if s['audio_path'] else '🔇 No audio'}</span>
  <div class="scene-visual">📷 {s['visual']}</div>
  <div style="color:#e2e8f0;font-size:0.82rem;margin-top:6px;font-style:italic">"{s['narration'][:100]}{'...' if len(s['narration'])>100 else ''}"</div>
</div>""", unsafe_allow_html=True)

    # Script
    if st.session_state.get("script"):
        with st.expander("✍️ View / Edit Script"):
            edited = st.text_area("Script", st.session_state["script"], height=300, label_visibility="collapsed")
            script_dl = f"REEL.AI Script\nTopic: {topic}\n\n{st.session_state['script']}"
            st.download_button("📄 Download Script (.txt)", script_dl, f"{fname[:-4]}_script.txt", "text/plain")

    st.markdown("---")
    if st.button("✨ Create Another Video", use_container_width=False):
        for key in ["video_bytes", "script", "scenes_data", "meta", "processed_scenes"]:
            st.session_state[key] = None
        st.rerun()

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("")
st.markdown(
    "<p style='text-align:center;color:#1e293b;font-size:0.78rem;'>REEL.AI · Built for Nepal 🇳🇵 & Creators Worldwide · Powered by Claude AI</p>",
    unsafe_allow_html=True,
)
