# Spotify Random Playlist Generator

Generates a new random Spotify playlist from your chosen “source” playlists, optionally excluding tracks found in your “main” playlists. Launches a GUI to choose how many songs, whether to exclude or immediately play, and to pick which playlist(s) to source from.

## Features
- Random track selection (artist’s same album, top tracks, discography, or plain random).
- Exclude tracks already in your main playlists if desired.
- Optionally start playback immediately on a detected Spotify device.
- Opens the newly created playlist in your browser and attempts to open in the Spotify desktop client.
- All configuration stored in a simple JSON file.

## Requirements
- Python 3.x
- [Spotipy](https://spotipy.readthedocs.io/) (`pip install spotipy`)
- A [Spotify Developer](https://developer.spotify.com/dashboard/) App (client ID & secret).

## Setup
1. **Create or edit your Spotify Developer app**:
   - In your app’s settings, add a redirect URI (e.g. `http://localhost:8080/callback`).
   - Copy the client ID and secret.

2. **Edit `my_config.json`**:
   ```json
   {
   "client_id": "YOUR_SPOTIFY_CLIENT_ID",
   "client_secret": "YOUR_SPOTIFY_CLIENT_SECRET",
   "redirect_uri": "http://localhost:8080/callback",
   "scope": "playlist-read-private playlist-modify-private user-read-private user-library-read user-modify-playback-state user-read-playback-state",
   "main_playlist_ids": [
    "YOUR_MAIN_PLAYLIST_ID_1",
    "YOUR_MAIN_PLAYLIST_ID_2"
   ],
   "featured_playlists": [
    {
      "id": "YOUR_FEATURED_PLAYLIST_ID",
      "name": "Some Playlist Name",
      "genres": "Short description here"
    }
   ]
   }



3. **Run the program**:
   - Directly with:
     ```
     python SpotifyRandomizer.py
     ```
   - **Or** via a `.bat` file (Windows). For example, `run.bat`:
     ```
     @echo off
     python SpotifyRandomizer.py
     pause
     ```

4. **Using the GUI**:
   - **Number of Songs**: Sets how many to generate.
   - **Exclude songs** in your main playlists if you don’t want repeats.
   - **Start Playing Now** toggles immediate playback.
   - **Generate from My Main Playlists** or any “featured” playlist you specify in the config.

## Notes
- If you want a public playlist, change `public=False` to `public=True` in the script.
- If you don’t exclude main playlists, you might get duplicates. That’s normal.
- Some tracks may be unavailable in the US region; they are skipped.
- Make sure you’ve followed or saved any playlist ID you reference in `my_config.json`, or you’ll get a 404 from Spotify.

Enjoy randomizing your Spotify playlists!
