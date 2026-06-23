// Playlists page JavaScript
document.addEventListener('DOMContentLoaded', () => {
    const playlistForm = document.getElementById('playlist-form');
    const playlistInput = document.getElementById('playlist-input');
    const downloadJsonBtn = document.getElementById('download-json');
    const generateM3UBtn = document.getElementById('generate-m3u');
    const scanMBAlbumsBtn = document.getElementById('scan-mb-albums');
    const sendToLidarrBtn = document.getElementById('send-to-lidarr');
    const userPlaylistsDiv = document.getElementById('user-playlists');
    const mbScanStatus = document.getElementById('mb-scan-status');
    const mbScanMessage = document.getElementById('mb-scan-message');

    // Track current MB file for Lidarr
    let currentMBFile = null;

    // Load user playlists on page load
    loadUserPlaylists();

    // Listen for MB scan complete event
    if (window.spotifyApp && window.spotifyApp.socket) {
        window.spotifyApp.socket.on('mb_scan_complete', (data) => {
            window.spotifyApp.hideProgress();
            currentMBFile = data.mb_file;

            // Enable Send to Lidarr button
            if (sendToLidarrBtn) {
                sendToLidarrBtn.disabled = false;
            }

            // Show status message
            if (mbScanStatus && mbScanMessage) {
                mbScanStatus.style.display = 'block';
                mbScanMessage.innerHTML = `<span class="text-success"><i class="fas fa-check-circle me-1"></i>${data.found} albums found</span>, <span class="text-warning">${data.failed} failed</span>`;
            }

            // Update track list with checkmarks for found albums
            if (data.found_albums) {
                window.spotifyApp.updateMBStatus(data.found_albums);
            }

            window.spotifyApp.showSuccess(data.message);
        });

        // Reset MB state when new playlist is fetched
        window.spotifyApp.socket.on('playlist_fetched', () => {
            currentMBFile = null;
            if (sendToLidarrBtn) {
                sendToLidarrBtn.disabled = true;
            }
            if (mbScanStatus) {
                mbScanStatus.style.display = 'none';
            }
        });
    }

    // Handle playlist form submission
    if (playlistForm) {
        playlistForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const playlistId = playlistInput.value.trim();
            
            if (!playlistId) {
                window.spotifyApp.showError('Please enter a playlist URL or ID');
                return;
            }

            await fetchPlaylist(playlistId);
        });
    }

    // Handle JSON download
    if (downloadJsonBtn) {
        downloadJsonBtn.addEventListener('click', async () => {
            if (!window.spotifyApp.currentTempFile) {
                window.spotifyApp.showError('Please fetch a playlist first');
                return;
            }

            await downloadFullJSON();
        });
    }

    // Handle M3U generation
    if (generateM3UBtn) {
        generateM3UBtn.addEventListener('click', async () => {
            if (!window.spotifyApp.currentTempFile) {
                window.spotifyApp.showError('Please fetch a playlist first');
                return;
            }

            await generateM3U();
        });
    }

    // Handle MB Albums scan
    if (scanMBAlbumsBtn) {
        scanMBAlbumsBtn.addEventListener('click', async () => {
            if (!window.spotifyApp.currentTempFile) {
                window.spotifyApp.showError('Please fetch a playlist first');
                return;
            }

            await scanMBAlbums();
        });
    }

    // Handle Lidarr submission
    if (sendToLidarrBtn) {
        sendToLidarrBtn.addEventListener('click', async () => {
            if (!currentMBFile) {
                window.spotifyApp.showError('Please scan MusicBrainz albums first');
                return;
            }

            await sendToLidarr();
        });
    }

    // Load user playlists
    async function loadUserPlaylists() {
        try {
            const response = await window.spotifyApp.makeRequest('/api/user-playlists');
            displayUserPlaylists(response.items || []);
        } catch (error) {
            console.error('Failed to load user playlists:', error);
            userPlaylistsDiv.innerHTML = `
                <div class="alert alert-warning">
                    <small>Unable to load your playlists. ${error.message}</small>
                </div>
            `;
        }
    }

    // Display user playlists
    function displayUserPlaylists(playlists) {
        if (!playlists.length) {
            userPlaylistsDiv.innerHTML = `
                <div class="text-muted text-center">
                    <i class="fas fa-music fa-2x mb-2"></i>
                    <p>No playlists found</p>
                </div>
            `;
            return;
        }

        const playlistsHtml = playlists.map(playlist => `
            <div class="playlist-item mb-2" data-playlist-id="${playlist.id}">
                <div class="d-flex align-items-center">
                    <div class="flex-shrink-0">
                        ${playlist.images && playlist.images[0] 
                            ? `<img src="${playlist.images[0].url}" alt="${playlist.name}" 
                                 class="rounded" style="width: 40px; height: 40px; object-fit: cover;">`
                            : `<div class="bg-secondary rounded d-flex align-items-center justify-content-center" 
                                 style="width: 40px; height: 40px;">
                                 <i class="fas fa-music text-white"></i>
                               </div>`
                        }
                    </div>
                    <div class="flex-grow-1 ms-3">
                        <h6 class="mb-1">${window.spotifyApp.escapeHtml(playlist.name)}</h6>
                        <small class="text-muted">${playlist.tracks?.total ?? '?'} tracks</small>
                    </div>
                </div>
            </div>
        `).join('');

        userPlaylistsDiv.innerHTML = playlistsHtml;

        // Add click handlers to playlist items
        document.querySelectorAll('.playlist-item').forEach(item => {
            item.addEventListener('click', () => {
                const playlistId = item.dataset.playlistId;
                playlistInput.value = playlistId;
                
                // Visual feedback
                document.querySelectorAll('.playlist-item').forEach(p => p.classList.remove('selected'));
                item.classList.add('selected');
            });
        });
    }

    // Fetch playlist data
    async function fetchPlaylist(playlistId) {
        try {
            window.spotifyApp.showProgress('Fetching Playlist');
            
            const response = await window.spotifyApp.makeRequest('/api/fetch-playlist', {
                method: 'POST',
                body: JSON.stringify({ playlist_id: playlistId })
            });

            // Progress updates will be handled by socket events
        } catch (error) {
            window.spotifyApp.hideProgress();
            window.spotifyApp.showError(`Failed to fetch playlist: ${error.message}`);
        }
    }

    // Generate M3U playlist
    async function generateM3U() {
        try {
            window.spotifyApp.showProgress('Generating M3U');
            
            const response = await window.spotifyApp.makeRequest('/api/generate-m3u', {
                method: 'POST',
                body: JSON.stringify({
                    temp_file: window.spotifyApp.currentTempFile,
                    playlist_name: window.spotifyApp.currentPlaylistName || 'spotify_playlist'
                })
            });

            // Progress updates will be handled by socket events
        } catch (error) {
            window.spotifyApp.hideProgress();
            window.spotifyApp.showError(`Failed to generate M3U: ${error.message}`);
        }
    }

    // Scan MusicBrainz albums
    async function scanMBAlbums() {
        try {
            window.spotifyApp.showProgress('Scanning MusicBrainz');

            const response = await window.spotifyApp.makeRequest('/api/scan-mb-albums', {
                method: 'POST',
                body: JSON.stringify({
                    temp_file: window.spotifyApp.currentTempFile,
                    playlist_name: window.spotifyApp.currentPlaylistName || 'playlist'
                })
            });

            // Progress updates will be handled by socket events
        } catch (error) {
            window.spotifyApp.hideProgress();
            window.spotifyApp.showError(`Failed to scan MusicBrainz: ${error.message}`);
        }
    }

    // Send to Lidarr
    async function sendToLidarr() {
        try {
            window.spotifyApp.showProgress('Sending to Lidarr');

            const response = await window.spotifyApp.makeRequest('/api/send-to-lidarr', {
                method: 'POST',
                body: JSON.stringify({
                    mb_file: currentMBFile
                })
            });

            // Progress updates will be handled by socket events
        } catch (error) {
            window.spotifyApp.hideProgress();
            window.spotifyApp.showError(`Failed to send to Lidarr: ${error.message}`);
        }
    }

    // Download full JSON data
    async function downloadFullJSON() {
        try {
            const response = await window.spotifyApp.makeRequest('/api/download-json', {
                method: 'POST',
                body: JSON.stringify({
                    temp_file: window.spotifyApp.currentTempFile,
                    filename: window.spotifyApp.currentPlaylistName || 'playlist'
                })
            });

            if (response.success) {
                window.spotifyApp.downloadJSON(response.data, window.spotifyApp.currentPlaylistName || 'playlist');
            } else {
                window.spotifyApp.showError('Failed to download JSON data');
            }
        } catch (error) {
            window.spotifyApp.showError(`Failed to download JSON: ${error.message}`);
        }
    }

    // Handle playlist URL input formatting
    if (playlistInput) {
        playlistInput.addEventListener('input', (e) => {
            let value = e.target.value.trim();
            
            // Extract playlist ID from URL if needed
            if (value.includes('spotify.com/playlist/')) {
                const match = value.match(/playlist\/([a-zA-Z0-9]+)/);
                if (match) {
                    e.target.value = match[1];
                }
            }
        });

        // Handle paste events
        playlistInput.addEventListener('paste', (e) => {
            setTimeout(() => {
                const event = new Event('input', { bubbles: true });
                e.target.dispatchEvent(event);
            }, 10);
        });
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Ctrl/Cmd + Enter to fetch playlist
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            if (document.activeElement === playlistInput) {
                playlistForm.dispatchEvent(new Event('submit'));
            }
        }
    });

    // Auto-focus playlist input
    if (playlistInput && !playlistInput.value) {
        playlistInput.focus();
    }
});
