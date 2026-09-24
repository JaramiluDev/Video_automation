import os
import random
import urllib.request
from PIL import Image, ImageDraw, ImageFont

class ThumbnailGenerator:
    def __init__(self, output_dir="data", assets_dir="data/assets"):
        self.output_dir = output_dir
        self.assets_dir = assets_dir
        self.font_path = os.path.join(output_dir, "Roboto-Black.ttf")
        os.makedirs(self.output_dir, exist_ok=True)
        self._ensure_font_exists()

    def _ensure_font_exists(self):
        if not os.path.exists(self.font_path):
            url = "https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Black.ttf"
            try:
                urllib.request.urlretrieve(url, self.font_path)
                print("⏬ Descargando fuente tipográfica Roboto-Black...")
            except Exception as e:
                print(f"❌ Error descargando la fuente: {e}")

    def get_random_file(self, folder_path):
        if not os.path.exists(folder_path):
            return None
        valid_extensions = ('.png', '.jpg', '.jpeg')
        files = [f for f in os.listdir(folder_path) if f.lower().endswith(valid_extensions)]
        return os.path.join(folder_path, random.choice(files)) if files else None

    def crop_transparent_borders(self, img):
        """MATA LA CAJA INVISIBLE: Recorta el espacio transparente alrededor del personaje."""
        bbox = img.getbbox()
        if bbox:
            return img.crop(bbox)
        return img

    def resize_character(self, img, target_height=600):
        # 1. Le volamos la transparencia invisible de los lados
        img = self.crop_transparent_borders(img)
        # 2. Ahora sí lo escalamos a su tamaño real
        aspect_ratio = img.width / img.height
        new_width = int(target_height * aspect_ratio)
        return img.resize((new_width, target_height), Image.Resampling.LANCZOS)

    def wrap_text(self, text, font, max_width, draw):
        words = text.split()
        lines = []
        current_line = ""
        for word in words:
            test_line = f"{current_line} {word}".strip()
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if (bbox[2] - bbox[0]) <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        return "\n".join(lines)

    def generate(self, title, output_filename="miniatura_final.jpg"):
        width, height = 1280, 720
        
        # 1. Selección aleatoria
        bg_path = self.get_random_file(os.path.join(self.assets_dir, "backgrounds"))
        jaime_path = self.get_random_file(os.path.join(self.assets_dir, "characters", "jaime"))
        agente0_path = self.get_random_file(os.path.join(self.assets_dir, "characters", "agente0"))

        # 2. Cargar Fondo con Zoom
        if bg_path:
            img = Image.open(bg_path).convert("RGBA")
            zoom_factor = 1.35
            new_w, new_h = int(width * zoom_factor), int(height * zoom_factor)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            left, top = (new_w - width) / 2, (new_h - height) / 2
            img = img.crop((left, top, left + width, top + height))
        else:
            img = Image.new('RGBA', (width, height), color='#1b3b22')

    # 3. Personajes (Grandes, en los bordes y cortados a medio cuerpo)
        if jaime_path:
            jaime_img = Image.open(jaime_path).convert("RGBA")
            jaime_img = self.resize_character(jaime_img, target_height=650) 
            # Lo pegamos a la izquierda (x=0) y lo bajamos 80px para cortar las piernas
            img.paste(jaime_img, (0, height - jaime_img.height + 233), jaime_img)

        if agente0_path:
            agente0_img = Image.open(agente0_path).convert("RGBA")
            agente0_img = self.resize_character(agente0_img, target_height=650)
            
            # Lo pegamos a la derecha y lo bajamos 80px para igualar proporciones
            x_agente0 = width - agente0_img.width
            y_agente0 = height - agente0_img.height + 250
            
            # ¡Aquí ya estamos usando las variables correctas!
            img.paste(agente0_img, (x_agente0, y_agente0), agente0_img)

        # 4. Formato de Pizarrón (Efecto Gis y Multilínea)
        try:
            font = ImageFont.truetype(self.font_path, 85)
        except Exception:
            return

        draw = ImageDraw.Draw(img)
        wrapped_title = self.wrap_text(title, font, max_width=750, draw=draw)
        
        bbox = draw.multiline_textbbox((0, 0), wrapped_title, font=font, align="center")
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        x = (width - text_w) / 2
        y = ((height - text_h) / 2) - 30 

        draw.multiline_text(
            (x, y), 
            wrapped_title, 
            font=font, 
            fill="#F4F4F0", 
            align="center",
            stroke_width=2, 
            stroke_fill="#A0A0A0" 
        )

        # 5. Exportar
        img = img.convert("RGB")
        output_path = os.path.join(self.output_dir, output_filename)
        img.save(output_path)
        print(f"🚀 ¡Miniatura dinámica renderizada en: {output_path}!")

if __name__ == "__main__":
    gen = ThumbnailGenerator(output_dir="data", assets_dir="data/assets")
    gen.generate(title="escribir titulo")