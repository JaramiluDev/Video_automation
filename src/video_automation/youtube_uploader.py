import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

class YouTubeUploader:
    def __init__(self, client_secrets_file):
        self.client_secrets_file = client_secrets_file
        self.token_file = 'token.json'
        self.scopes = ['https://www.googleapis.com/auth/youtube.upload']

    def authenticate(self):
        creds = None
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, self.scopes)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_file, self.scopes)
                creds = flow.run_local_server(port=8080, open_browser=False)
            
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
                
        return build('youtube', 'v3', credentials=creds)

    def upload_video(self, youtube_service, file_path, title, description, tags, category_id="27"):
        try:
            body = {
                'snippet': {
                    'title': title,
                    'description': description,
                    'tags': tags,
                    'categoryId': category_id
                },
                'status': {
                    'privacyStatus': 'private' 
                }
            }
            media = MediaFileUpload(file_path, mimetype='video/*')
            
            print(f"Subiendo video: '{title}' a YouTube...")
            insert_request = youtube_service.videos().insert(
                body=body,
                media_body=media,
                part='snippet,status'
            )
            response = insert_request.execute()
            print(f"✅ ¡Video subido exitosamente! ID: {response.get('id')}")
            return response
            
        except Exception as e:
            print(f"❌ Error al subir el video: {e}")
            return None