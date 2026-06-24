// Liked Songs page JavaScript
document.addEventListener('DOMContentLoaded', () => {
    const fetchLikedBtn = document.getElementById('fetch-liked-songs');
    const downloadJsonBtn = document.getElementById('download-json-liked');
    const generateM3UBtn = document.getElementById('generate-m3u-liked');
    const sendToLidarrBtn = document.getElementById('send-to-lidarr-liked');
    const splitPlaylistsBtn = document.getElementById('split-playlists');
    const confirmSplitBtn = document.getElementById('confirm-split');
    const confirmSplitFinalBtn = document.getElementById('confirm-split-final');
    const splitSettingsDiv = document.getElementById('split-settings');

    // Load the total liked-songs count on page mount
    loadLikedSongsCount();

    // Handle fetch liked songs
    if (fetchLikedBtn) {
        fetchLikedBtn.addEventListener('click', async () => {
            await fetchLikedSongs();
        });
    }

    async function loadLikedSongsCount() {
        const countDisplay = document.getElementById('liked-count-display');
        const countValue = document.getElementById('liked-count-value');
        if (!countDisplay || !countValue) return;

        try {
            const response = await window.spotifyApp.makeRequest('/api/liked-songs-count');
            if (typeof response.total === 'number') {
                countValue.textContent = response.total.toLocaleString();
            } else {
                countDisplay.style.display = 'none';
            }
        } catch (error) {
            countDisplay.style.display = 'none';
        }
    }

    // Handle JSON download
    if (downloadJsonBtn) {
        downloadJsonBtn.addEventListener('click', async () => {
            if (!window.spotifyApp.currentTempFile) {
                window.spotifyApp.showError('Please fetch your liked songs first');
                return;
            }

            await downloadFullJSON();
        });
    }

    // Handle M3U generation
    if (generateM3UBtn) {
        generateM3UBtn.addEventListener('click', async () => {
            if (!window.spotifyApp.currentTempFile) {
                window.spotifyApp.showError('Please fetch your liked songs first');
                return;
            }

            await generateM3U();
        });
    }

    // Handle Lidarr submission
    if (sendToLidarrBtn) {
        sendToLidarrBtn.addEventListener('click', async () => {
            if (!window.spotifyApp.currentTempFile) {
                window.spotifyApp.showError('Please fetch your liked songs first');
                return;
            }

            await sendToLidarr();
        });
    }

    // Handle split playlists button
    if (splitPlaylistsBtn) {
        splitPlaylistsBtn.addEventListener('click', () => {
            if (!window.spotifyApp.currentTempFile) {
                window.spotifyApp.showError('Please fetch your liked songs first');
                return;
            }

            // Show split settings
            splitSettingsDiv.style.display = 'block';
            splitSettingsDiv.scrollIntoView({ behavior: 'smooth' });
        });
    }

    // Handle confirm split button
    if (confirmSplitBtn) {
        confirmSplitBtn.addEventListener('click', () => {
            showSplitConfirmation();
        });
    }

    // Handle final split confirmation
    if (confirmSplitFinalBtn) {
        confirmSplitFinalBtn.addEventListener('click', async () => {
            const modal = bootstrap.Modal.getInstance(document.getElementById('splitModal'));
            modal.hide();
            await performSplit();
        });
    }

    // Fetch liked songs
    async function fetchLikedSongs() {
        try {
            window.spotifyApp.showProgress('Fetching Liked Songs');
            
            const response = await window.spotifyApp.makeRequest('/api/fetch-liked-songs', {
                method: 'POST'
            });

            // Progress updates will be handled by socket events
        } catch (error) {
            window.spotifyApp.hideProgress();
            window.spotifyApp.showError(`Failed to fetch liked songs: ${error.message}`);
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
                    playlist_name: 'liked_songs'
                })
            });

            // Progress updates will be handled by socket events
        } catch (error) {
            window.spotifyApp.hideProgress();
            window.spotifyApp.showError(`Failed to generate M3U: ${error.message}`);
        }
    }

    // Send to Lidarr
    async function sendToLidarr() {
        try {
            window.spotifyApp.showProgress('Sending to Lidarr');
            
            const response = await window.spotifyApp.makeRequest('/api/send-to-lidarr', {
                method: 'POST',
                body: JSON.stringify({
                    temp_file: window.spotifyApp.currentTempFile
                })
            });

            // Progress updates will be handled by socket events
        } catch (error) {
            window.spotifyApp.hideProgress();
            window.spotifyApp.showError(`Failed to send to Lidarr: ${error.message}`);
        }
    }

    // Show split confirmation modal
    function showSplitConfirmation() {
        const playlistSize = parseInt(document.getElementById('playlist-size').value);
        const playlistPrefix = document.getElementById('playlist-prefix').value.trim();
        
        if (!playlistPrefix) {
            window.spotifyApp.showError('Please enter a playlist name prefix');
            return;
        }

        if (playlistSize < 50 || playlistSize > 1000) {
            window.spotifyApp.showError('Playlist size must be between 50 and 1000 songs');
            return;
        }

        // Estimate number of playlists (we don't know exact count yet, so use a placeholder)
        const estimatedPlaylists = Math.ceil(1000 / playlistSize); // Rough estimate
        
        const confirmationMessage = document.getElementById('split-confirmation-message');
        confirmationMessage.innerHTML = `
            <p>This will create multiple playlists with up to <strong>${playlistSize}</strong> songs each.</p>
            <p>Playlist names will be: "<strong>${playlistPrefix} 1</strong>", "<strong>${playlistPrefix} 2</strong>", etc.</p>
            <p class="text-warning"><i class="fas fa-exclamation-triangle me-1"></i>
            This will create new playlists in your Spotify account.</p>
        `;

        const modal = new bootstrap.Modal(document.getElementById('splitModal'));
        modal.show();
    }

    // Perform the actual split
    async function performSplit() {
        const playlistSize = parseInt(document.getElementById('playlist-size').value);
        const playlistPrefix = document.getElementById('playlist-prefix').value.trim();

        try {
            window.spotifyApp.showProgress('Splitting Liked Songs');
            
            const response = await window.spotifyApp.makeRequest('/api/split-liked-songs', {
                method: 'POST',
                body: JSON.stringify({
                    temp_file: window.spotifyApp.currentTempFile,
                    playlist_size: playlistSize,
                    playlist_prefix: playlistPrefix
                })
            });

            // Progress updates will be handled by socket events
        } catch (error) {
            window.spotifyApp.hideProgress();
            window.spotifyApp.showError(`Failed to split liked songs: ${error.message}`);
        }
    }

    // Download full JSON data
    async function downloadFullJSON() {
        try {
            const response = await window.spotifyApp.makeRequest('/api/download-json', {
                method: 'POST',
                body: JSON.stringify({
                    temp_file: window.spotifyApp.currentTempFile,
                    filename: 'liked_songs'
                })
            });

            if (response.success) {
                window.spotifyApp.downloadJSON(response.data, 'liked_songs');
            } else {
                window.spotifyApp.showError('Failed to download JSON data');
            }
        } catch (error) {
            window.spotifyApp.showError(`Failed to download JSON: ${error.message}`);
        }
    }

    // Input validation
    const playlistSizeInput = document.getElementById('playlist-size');
    const playlistPrefixInput = document.getElementById('playlist-prefix');

    if (playlistSizeInput) {
        playlistSizeInput.addEventListener('input', (e) => {
            const value = parseInt(e.target.value);
            if (value < 50) {
                e.target.value = 50;
            } else if (value > 1000) {
                e.target.value = 1000;
            }
        });
    }

    if (playlistPrefixInput) {
        playlistPrefixInput.addEventListener('input', (e) => {
            // Remove invalid characters for playlist names
            e.target.value = e.target.value.replace(/[<>:"/\\|?*]/g, '');
        });
    }

    // Auto-focus fetch button if no data loaded
    if (fetchLikedBtn && !window.spotifyApp.currentTempFile) {
        // Small delay to ensure page is fully loaded
        setTimeout(() => {
            fetchLikedBtn.focus();
        }, 100);
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Ctrl/Cmd + L to fetch liked songs
        if ((e.ctrlKey || e.metaKey) && e.key === 'l') {
            e.preventDefault();
            if (fetchLikedBtn) {
                fetchLikedBtn.click();
            }
        }
    });
});

// Add split functionality to the main app
if (window.spotifyApp) {
    // Add socket handler for split completion
    window.spotifyApp.socket.on('split_complete', (data) => {
        window.spotifyApp.hideProgress();
        window.spotifyApp.showSuccess(
            `Successfully created ${data.playlist_count} playlists with your liked songs!`
        );
        
        // Hide split settings after successful split
        const splitSettingsDiv = document.getElementById('split-settings');
        if (splitSettingsDiv) {
            splitSettingsDiv.style.display = 'none';
        }
    });
}
