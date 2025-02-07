import tkinter as tk
from tkinter import ttk
import random
import webbrowser
import os
import subprocess
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import json
import sys
import re
import threading

#####################################################
# Debug Logging
#####################################################

def dbg(msg):
    """Prints a debug message to the console."""
    print(f"DEBUG: {msg}")

#####################################################
# Load Configuration from JSON
#####################################################

CONFIG_FILE = "my_config.json"
try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
except Exception as e:
    print(f"Failed to load {CONFIG_FILE}: {e}")
    sys.exit(1)

CLIENT_ID = config.get("client_id", "")
CLIENT_SECRET = config.get("client_secret", "")
REDIRECT_URI = config.get("redirect_uri", "http://localhost:8080/callback")
SCOPE = config.get("scope", "playlist-read-private playlist-modify-private")

MAIN_PLAYLIST_IDS = config.get("main_playlist_ids", [])
FEATURED_PLAYLISTS = config.get("featured_playlists", [])

#####################################################
# SpotifyRandomizer
#####################################################
class SpotifyRandomizer:
    """
    Handles Spotify authentication, track gathering, and
    random playlist creation.
    """
    def __init__(self):
        # Spotify client, user info
        self.sp = None
        self.user_id = None

        # GUI toggles
        self.exclude_main = False
        self.start_playback = True

        # For excluding main-playlist tracks
        self.main_tracks_set = set()

    def authenticate(self):
        """Authenticates with Spotify using OAuth, logs user info."""
        dbg("Authenticating with Spotify...")
        auth_manager = SpotifyOAuth(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri=REDIRECT_URI,
            scope=SCOPE,
            cache_path="my_token_cache.json",
            show_dialog=True
        )
        self.sp = spotipy.Spotify(auth_manager=auth_manager)
        token_info = auth_manager.get_cached_token()
        if not token_info:
            dbg("No token found. Expecting browser login.")
        else:
            dbg("Found cached token.")

        try:
            me = self.sp.current_user()
            self.user_id = me["id"]
            # keep debug text exactly the same
            dbg(f"Authenticated as user: {self.user_id} (" + me.get("display_name","No Name") + ")")
        except Exception as e:
            dbg(f"Authentication failed: {e}")
            raise RuntimeError(f"Spotify auth failed: {e}")

    def gather_playlist_tracks(self, playlist_id):
        """Fetch all track IDs from a single playlist (logs debug)."""
        dbg(f"Scanning playlist: {playlist_id}")
        all_track_ids = []
        try:
            results = self.sp.playlist_items(playlist_id, additional_types=['track'])
            tracks = results["items"]
            while results["next"]:
                results = self.sp.next(results)
                tracks.extend(results["items"])
            for t in tracks:
                td = t["track"]
                if td and not td.get("is_local"):
                    tid = td.get("id")
                    if tid:
                        all_track_ids.append(tid)
        except spotipy.exceptions.SpotifyException as e:
            if e.http_status == 404:
                dbg(f"Playlist {playlist_id} not found or inaccessible.")
            else:
                dbg(f"SpotifyException while fetching playlist {playlist_id}: {e}")
        except Exception as ex:
            dbg(f"Error fetching playlist {playlist_id}: {ex}")
        dbg(f"Found {len(all_track_ids)} valid tracks in playlist: {playlist_id}")
        return all_track_ids

    def gather_multiple_playlists_with_progress(self, playlist_ids, progress_callback=None, current_step=0, total_steps=1):
        """
        Fetch track IDs from multiple playlists, calling the
        progress_callback after each is loaded.
        Returns the combined list and the new current_step.
        """
        all_ids = []
        for pid in playlist_ids:
            tracks = self.gather_playlist_tracks(pid)
            if tracks:
                all_ids.extend(tracks)
            current_step += 1
            if progress_callback:
                progress_callback(current_step, total_steps)
        return all_ids, current_step

    def get_track_info(self, track_id):
        """Returns (name, "artist1, artist2") for a track_id."""
        try:
            tr = self.sp.track(track_id)
            name = tr["name"]
            arts = ", ".join(a["name"] for a in tr["artists"])
            return name, arts
        except:
            return ("Unknown Track", "Unknown Artist")

    def remove_parentheses(self, text):
        """Removes parentheses and enclosed text (e.g. 'Song (Live)' -> 'Song')."""
        return re.sub(r'\\s*\(.*?\)\\s*', '', text)

    ########################################################
    # Random Track-Picking Methods
    ########################################################

    def method_random_from_source(self, source_tracks):
        """Pick a random track from the given source list."""
        return random.choice(source_tracks)

    def method_same_album(self, seed_track_id):
        """Pick a random track from the same album as the seed."""
        try:
            seed_info = self.sp.track(seed_track_id)
            album_id = seed_info["album"]["id"]
            album_tracks_res = self.sp.album_tracks(album_id)
            album_tracks = album_tracks_res["items"]
            while album_tracks_res["next"]:
                album_tracks_res = self.sp.next(album_tracks_res)
                album_tracks.extend(album_tracks_res["items"])
            track_ids = [t["id"] for t in album_tracks if t.get("id")]
            if track_ids:
                return random.choice(track_ids)
            else:
                return seed_track_id
        except Exception as e:
            dbg(f"Error in method_same_album: {e}")
            return seed_track_id

    def method_artist_top_tracks(self, seed_track_id):
        """Pick a random track from a random artist's top tracks."""
        try:
            seed_info = self.sp.track(seed_track_id)
            artists = seed_info["artists"]
            if not artists:
                return seed_track_id
            artist = random.choice(artists)
            artist_id = artist["id"]
            top_tracks_data = self.sp.artist_top_tracks(artist_id, country="US")
            top_ids = [t["id"] for t in top_tracks_data["tracks"]]
            if top_ids:
                return random.choice(top_ids)
            else:
                return seed_track_id
        except Exception as e:
            dbg(f"Error in method_artist_top_tracks: {e}")
            return seed_track_id

    def method_artist_discography(self, seed_track_id):
        """Pick a random track from a random artist's entire discography."""
        try:
            seed_info = self.sp.track(seed_track_id)
            artists = seed_info["artists"]
            if not artists:
                return seed_track_id
            artist = random.choice(artists)
            artist_id = artist["id"]
            album_ids = []
            results = self.sp.artist_albums(artist_id, album_type="album,single", country="US")
            albums = results["items"]
            while results["next"]:
                results = self.sp.next(results)
                albums.extend(results["items"])
            for a in albums:
                if a.get("id"):
                    album_ids.append(a["id"])
            if not album_ids:
                return seed_track_id
            random_album_id = random.choice(album_ids)
            tracks_res = self.sp.album_tracks(random_album_id)
            album_tracks = tracks_res["items"]
            while tracks_res["next"]:
                tracks_res = self.sp.next(tracks_res)
                album_tracks.extend(tracks_res["items"])
            possible_ids = [t["id"] for t in album_tracks if t.get("id")]
            if possible_ids:
                return random.choice(possible_ids)
            else:
                return seed_track_id
        except Exception as e:
            dbg(f"Error in method_artist_discography: {e}")
            return seed_track_id

    ########################################################
    # Main Playlist Creation Method
    ########################################################

    def create_random_playlist(self, source_playlist_ids, song_count, progress_callback=None):
        """
        Gathers tracks from source_playlist_ids, optionally excludes main-playlist
        tracks, picks random songs with various methods, then creates a new Spotify
        playlist. Also opens it in browser/desktop, optionally starts playback.
        """
        total_steps = len(source_playlist_ids)
        if self.exclude_main:
            total_steps += len(MAIN_PLAYLIST_IDS)
        total_steps += song_count
        current_step = 0

        dbg("Gathering source tracks...")
        source_tracks, current_step = self.gather_multiple_playlists_with_progress(
            source_playlist_ids,
            progress_callback=progress_callback,
            current_step=current_step,
            total_steps=total_steps
        )
        dbg(f"Total source tracks gathered: {len(source_tracks)}")
        if not source_tracks:
            raise ValueError("No valid source tracks found.")

        if self.exclude_main:
            dbg("Gathering main‐playlist tracks for exclusion...")
            main_tracks, current_step = self.gather_multiple_playlists_with_progress(
                MAIN_PLAYLIST_IDS,
                progress_callback=progress_callback,
                current_step=current_step,
                total_steps=total_steps
            )
            self.main_tracks_set = set(main_tracks)
            dbg(f"Total main tracks for exclusion: {len(self.main_tracks_set)}")
        else:
            self.main_tracks_set = set()

        final_tracks = []
        for i in range(song_count):
            chosen_id = None
            attempts = 0
            while chosen_id is None and attempts < 30:
                attempts += 1
                method_choice = random.randint(1, 4)
                seed_track_id = random.choice(source_tracks)

                dbg(f"Attempt {attempts} for song #{i+1}, method {method_choice}, seed={seed_track_id}")

                if method_choice == 1:
                    cand_id = self.method_random_from_source(source_tracks)
                elif method_choice == 2:
                    cand_id = self.method_same_album(seed_track_id)
                elif method_choice == 3:
                    cand_id = self.method_artist_top_tracks(seed_track_id)
                else:
                    cand_id = self.method_artist_discography(seed_track_id)

                if self.exclude_main and cand_id in self.main_tracks_set:
                    dbg(f"Candidate track {cand_id} is in main playlists, skipping.")
                    continue

                # Check if track is playable in the US
                try:
                    cand_info = self.sp.track(cand_id)
                    markets = cand_info.get("available_markets", [])
                    if "US" not in markets:
                        dbg(f"Candidate track {cand_id} not playable in US, skipping.")
                        continue
                except Exception as e:
                    dbg(f"Error checking track availability for {cand_id}: {e}")
                    continue

                chosen_id = cand_id
                dbg(f"Song #{i+1} selected: {cand_id}")

            if chosen_id is None:
                raise ValueError("Couldn't find enough valid tracks to fill your desired playlist size.")

            final_tracks.append(chosen_id)
            current_step += 1
            if progress_callback:
                progress_callback(current_step, total_steps)

        # Build a name from two random songs
        if len(final_tracks) >= 2:
            random_name_tracks = random.sample(final_tracks, 2)
        else:
            random_name_tracks = final_tracks
        s1_name, _ = self.get_track_info(random_name_tracks[0])
        s2_name, _ = self.get_track_info(random_name_tracks[1]) if len(random_name_tracks) > 1 else ("Unknown", "")
        s1_clean = self.remove_parentheses(s1_name)
        s2_clean = self.remove_parentheses(s2_name)
        playlist_name = f"{s1_clean} {s2_clean}"

        dbg(f"Creating new playlist: {playlist_name}")
        try:
            new_pl = self.sp.user_playlist_create(self.user_id, name=playlist_name, public=False)
            self.sp.playlist_add_items(new_pl["id"], final_tracks)
            dbg(f"Created new playlist: {new_pl['id']}")

            # Open in browser
            playlist_url = new_pl["external_urls"]["spotify"]
            webbrowser.open(playlist_url)

            # Try opening in desktop
            desktop_uri = f"spotify:playlist:{new_pl['id']}"
            try:
                if os.name == 'nt':
                    os.startfile(desktop_uri)
                elif os.name == 'posix':
                    subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', desktop_uri])
            except Exception as e:
                dbg(f"Failed to open Spotify app: {e}")

            if self.start_playback:
                dbg("Starting playlist playback...")
                try:
                    devices = self.sp.devices()
                    if devices['devices']:
                        device_id = devices['devices'][0]['id']
                        self.sp.shuffle(False, device_id=device_id)
                        self.sp.repeat('context', device_id=device_id)
                        self.sp.start_playback(device_id=device_id, context_uri=desktop_uri)
                    else:
                        dbg("No active Spotify devices found for playback.")
                except Exception as e:
                    dbg(f"Failed to set playback: {e}")
            else:
                dbg("User opted not to start playback. Done.")

            return playlist_url
        except spotipy.exceptions.SpotifyException as e:
            raise RuntimeError(f"Failed to create playlist: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to create playlist: {e}")

#####################################################
# GUI
#####################################################

class RandomSongGUI:
    """
    Builds the Tkinter-based GUI, handles user interaction,
    passes calls to the SpotifyRandomizer.
    """
    def __init__(self, root):
        self.root = root
        self.root.title("Random Song Generator")
        self.root.configure(bg="#111111")

        # Add random color picking
        neon_colors = [
            "#E6E6FA",  # Pale Light Lavender Purple
            "#FFB6C1",  # Pale Light Pink
            "#AFEEEE",  # Pale Light Cyan
            "#98FB98",  # Pale Light Lime Green
            "#FF7F7F",  # Pale Light Red
            "#ADD8E6",  # Pale Light Blue
            "#F0F8FF",  # Pale White
            "#FFFFE0",  # Pale Light Yellow
            "#FFDAB9",  # Pale Light Orange
            "#8A2BE2",  # Pale Light Indigo
            "#FF77FF",  # Pale Light Reddish-Pink
            "#20B2AA",  # Pale Light Teal
            "#4169E1",  # Lighter Deep Blue (RoyalBlue)
            "#FF77FF"   # Pale Light Magenta
        ]
        self.theme_color = random.choice(neon_colors)
        dbg(f"Selected theme color: {self.theme_color}")

        # TTK styling
        style = ttk.Style(self.root)
        style.theme_use("clam")

        # Use randomly chosen theme_color for foreground
        style.configure(".", background="#111111", foreground=self.theme_color, font=("Segoe UI", 10))
        style.configure("TFrame", background="#111111")
        style.configure("TLabel", background="#111111", foreground=self.theme_color)
        style.configure("TButton",
                        background="#1e1e1e",
                        foreground=self.theme_color,
                        borderwidth=2,
                        focusthickness=3,
                        focuscolor=self.theme_color)
        style.map("TButton",
                  background=[("active", "#333333")],
                  foreground=[("active", self.theme_color)])
        style.configure("TScale",
                        background="#111111",
                        troughcolor="#000000",
                        troughrelief="flat")
        style.map("TScale", background=[("active", self.theme_color)])
        style.configure("custom.Horizontal.TProgressbar",
                        troughcolor="#000000",
                        background="#FFFFFF",
                        bordercolor="#000000",
                        lightcolor="#000000",
                        darkcolor="#000000")

        self.root.update_idletasks()

        # Main container
        self.container = ttk.Frame(root, padding=15)
        self.container.grid(sticky="nsew")
        root.rowconfigure(0, weight=1)
        root.columnconfigure(0, weight=1)
        self.container.columnconfigure(0, weight=1)

        # Create the randomizer
        self.api = SpotifyRandomizer()
        self.api.authenticate()

        #################################################
        # Big button
        #################################################
        big_button = ttk.Button(
            self.container,
            text="Generate Random Playlist (From My Main Playlists)",
            command=self.on_big_button_click
        )
        big_button.grid(row=0, column=0, sticky="ew", pady=(0,15))

        #################################################
        # Song count slider
        #################################################
        song_count_frame = ttk.Frame(self.container)
        song_count_frame.grid(row=1, column=0, sticky="ew", pady=(0,15))
        ttk.Label(song_count_frame, text="Number of Songs:").pack(side="left")

        self.song_count_var = tk.IntVar(value=15)
        song_count_slider = ttk.Scale(
            song_count_frame, from_=1, to=50, orient="horizontal",
            variable=self.song_count_var, length=300,
            command=self.update_song_count_label
        )
        song_count_slider.pack(side="left", padx=(10,10))
        self.song_count_display = ttk.Label(song_count_frame, text=str(self.song_count_var.get()))
        self.song_count_display.pack(side="left")

        #################################################
        # Exclude main checkbox
        #################################################
        self.exclude_main_var = tk.BooleanVar(value=False)
        exclude_main_check = tk.Checkbutton(
            self.container,
            text="Exclude songs already on my main playlists",
            variable=self.exclude_main_var,
            onvalue=True,
            offvalue=False,
            fg=self.theme_color,
            bg="#111111",
            selectcolor="#333333"
        )
        exclude_main_check.grid(row=2, column=0, sticky="w", pady=(0, 5))

        #################################################
        # Start Playing checkbox
        #################################################
        self.start_play_var = tk.BooleanVar(value=True)
        start_play_check = tk.Checkbutton(
            self.container,
            text="Start Playing Now",
            variable=self.start_play_var,
            onvalue=True,
            offvalue=False,
            fg=self.theme_color,
            bg="#111111",
            selectcolor="#333333"
        )
        start_play_check.grid(row=3, column=0, sticky="w", pady=(0, 15))

        #################################################
        # Featured playlists
        #################################################
        ttk.Label(
            self.container,
            text="Featured Playlists:",
            font=("Segoe UI", 12, "bold"),
            foreground=self.theme_color,
            background="#111111"
        ).grid(row=4, column=0, sticky="w", pady=(0,5))

        start_row = 5
        for idx, fp in enumerate(FEATURED_PLAYLISTS):
            self.add_featured_playlist_row(fp, start_row + idx)

        # Loading frame + progress bar
        self.loading_frame = ttk.Frame(self.container)
        self.loading_frame.grid(row=start_row + len(FEATURED_PLAYLISTS), column=0, pady=20)
        self.progress = ttk.Progressbar(
            self.loading_frame,
            style="custom.Horizontal.TProgressbar",
            mode='determinate',
            length=400
        )
        self.progress.pack(pady=5)
        self.progress.grid_remove()

        # Status label
        self.status_label = ttk.Label(self.container, text="", foreground=self.theme_color, background="#111111")
        self.status_label.grid(row=start_row + len(FEATURED_PLAYLISTS) + 1, column=0, sticky="ew", pady=10)

        self.center_window()

    def center_window(self):
        """Auto-size to fit content, then center on screen."""
        self.root.update_idletasks()
        w = self.root.winfo_reqwidth()
        h = self.root.winfo_reqheight()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def add_featured_playlist_row(self, fp_info, row_idx):
        """Creates a row in the GUI for one featured playlist."""
        frame = ttk.Frame(self.container)
        frame.grid(row=row_idx, column=0, sticky="ew", pady=5)
        lbl_name = ttk.Label(frame, text=fp_info["name"], font=("Segoe UI", 11, "bold"), foreground=self.theme_color, background="#111111")
        lbl_name.pack(side="top", anchor="w")
        lbl_genres = ttk.Label(frame, text=fp_info["genres"], font=("Segoe UI", 9, "italic"), foreground=self.theme_color, background="#111111")
        lbl_genres.pack(side="top", anchor="w")
        btn = ttk.Button(
            frame,
            text="Generate from This Playlist",
            command=lambda pid=fp_info["id"]: self.on_featured_button_click(pid)
        )
        btn.pack(side="right", padx=10)

    def update_song_count_label(self, value):
        """Updates the displayed number of songs as slider moves."""
        self.song_count_display.config(text=str(int(float(value))))

    def on_big_button_click(self):
        """Called when the main big button is clicked."""
        song_limit = self.song_count_var.get()
        self.status_label.config(text=f"Generating random playlist ({song_limit} songs) from main playlists...")
        self.start_generation(MAIN_PLAYLIST_IDS, song_limit)

    def on_featured_button_click(self, playlist_id):
        """Called when a featured playlist's generate button is clicked."""
        song_limit = self.song_count_var.get()
        self.status_label.config(text=f"Generating random playlist ({song_limit} songs) from featured playlist...")
        self.start_generation([playlist_id], song_limit)

    def start_generation(self, playlist_ids, song_count):
        """Prepares the progress bar, spawns thread to generate the playlist."""
        self.loading_frame.grid()
        self.progress.pack()
        self.progress['value'] = 0
        self.progress['maximum'] = 100
        threading.Thread(
            target=self.generate_playlist,
            args=(playlist_ids, song_count),
            daemon=True
        ).start()

    def generate_playlist(self, playlist_ids, song_count):
        """In a separate thread, calls create_random_playlist, updates status."""
        try:
            self.api.exclude_main = self.exclude_main_var.get()
            self.api.start_playback = self.start_play_var.get()
            self.api.create_random_playlist(
                playlist_ids,
                song_count,
                progress_callback=self.update_progress
            )
            msg = "Playlist created!"
            if self.api.start_playback:
                msg += " Playing and closing..."
            self.root.after(0, lambda: self.status_label.config(text=msg))
        except Exception as e:
            self.root.after(0, lambda: self.status_label.config(text=f"Error: {e}"))
            dbg(f"Error: {e}")
        finally:
            self.root.after(0, self.stop_loading_and_close)

    def update_progress(self, current, total):
        """Updates the progress bar and status label with the current progress."""
        pct = (current / total) * 100
        self.progress['value'] = pct
        self.root.after(0, lambda: self.status_label.config(
            text=f"Generating... {int(pct)}% (Step {current}/{total})"
        ))

    def stop_loading_and_close(self):
        """Hides progress bar, then closes the app after a delay."""
        self.progress.pack_forget()
        self.root.after(1500, self.close_app)

    def close_app(self):
        """Closes GUI and exits the script."""
        dbg("Closing GUI and exiting.")
        self.root.destroy()
        os._exit(0)

#####################################################
# Main
#####################################################
def main():
    """Creates the Tkinter root, tries setting an icon, runs the GUI."""
    root = tk.Tk()

    # Attempt to set a custom icon
    try:
        circle_data = """
R0lGODlhEAAQAPMAAAAAAP///+bm5v7+/tbW1vn5+ebm5uTk5PLy8t3d3dfX19fX1+b29v///yH5BAEAAA8ALAAAAAAQABAAAAQ7UMlJgQ6W0S9z17C1dQGhuG3hsrt60ZQIAOw==
""".strip()
        icon_img = tk.PhotoImage(data=circle_data)
        root.iconphoto(False, icon_img)
    except Exception as e:
        dbg(f"Failed to set custom icon: {e}")

    app = RandomSongGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
