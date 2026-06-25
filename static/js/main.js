// Main JavaScript for Spotify Migration Tool
class SpotifyMigrationApp {
    constructor() {
        this.socket = null;
        this.currentTempFile = null;
        this.currentPlaylistName = null;
        this.currentPlaylistData = null;
        this.currentLikedSongsData = null;
        this.foundAlbums = [];  // Albums found in MusicBrainz
        this.currentPage = 1;
        this.tracksPerPage = 50;
        this.init();
    }

    init() {
        this.initSocket();
        this.bindEvents();
        this.loadUserProfile();
    }

    initSocket() {
        this.socket = io();
        
        this.socket.on('progress', (data) => {
            this.updateProgress(data.message, data.progress);
        });

        this.socket.on('error', (data) => {
            this.hideProgress();
            this.showError(data.message);
        });

        this.socket.on('playlist_fetched', (data) => {
            this.hideProgress();
            this.handlePlaylistFetched(data);
        });

        this.socket.on('liked_songs_fetched', (data) => {
            this.hideProgress();
            this.handleLikedSongsFetched(data);
        });

        this.socket.on('m3u_generated', (data) => {
            this.hideProgress();
            this.handleM3UGenerated(data);
        });

        this.socket.on('lidarr_complete', (data) => {
            this.hideProgress();
            this.handleLidarrComplete(data);
        });
    }

    bindEvents() {
        // Global error handling
        window.addEventListener('error', (e) => {
            console.error('JavaScript error:', e.error);
        });

        // Handle form submissions
        document.addEventListener('submit', (e) => {
            e.preventDefault();
        });
    }

    // Progress handling
    showProgress(title = 'Processing...') {
        const modal = document.getElementById('progressModal');
        const titleElement = modal.querySelector('.modal-title');
        const progressBar = modal.querySelector('.progress-bar');
        const messageElement = document.getElementById('progress-message');
        const closeButton = document.getElementById('close-progress');

        titleElement.textContent = title;
        progressBar.style.width = '0%';
        messageElement.textContent = 'Starting...';
        closeButton.style.display = 'none';

        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    }

    updateProgress(message, progress) {
        const progressBar = document.querySelector('#progressModal .progress-bar');
        const messageElement = document.getElementById('progress-message');
        const closeButton = document.getElementById('close-progress');

        if (progressBar) {
            progressBar.style.width = `${progress}%`;
            progressBar.setAttribute('aria-valuenow', progress);
        }

        if (messageElement) {
            messageElement.textContent = message;
        }

        // Show close button when complete
        if (progress >= 100 && closeButton) {
            closeButton.style.display = 'block';
        }
    }

    hideProgress() {
        const modalElement = document.getElementById('progressModal');
        if (modalElement) {
            const modal = bootstrap.Modal.getInstance(modalElement);
            if (modal) {
                // Dispose completely destroys the modal instance
                modal.dispose();
            }
            // Clean up any lingering modal state
            modalElement.classList.remove('show');
            modalElement.style.display = 'none';
            modalElement.setAttribute('aria-hidden', 'true');
            modalElement.removeAttribute('aria-modal');
            modalElement.removeAttribute('role');
        }
        // Remove any leftover backdrops
        document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
        // Reset body scroll
        document.body.classList.remove('modal-open');
        document.body.style.removeProperty('overflow');
        document.body.style.removeProperty('padding-right');
    }

    // Error handling
    showError(message) {
        const modal = document.getElementById('errorModal');
        const messageElement = document.getElementById('error-message');
        
        messageElement.textContent = message;
        
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    }

    // Success handling
    showSuccess(message, downloadUrl = null) {
        const modal = document.getElementById('successModal');
        const messageElement = document.getElementById('success-message');
        const downloadLink = document.getElementById('download-link');
        const downloadBtn = document.getElementById('download-btn');

        messageElement.textContent = message;

        if (downloadUrl) {
            downloadBtn.href = downloadUrl;
            downloadLink.style.display = 'block';
        } else {
            downloadLink.style.display = 'none';
        }

        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    }

    // API helpers
    async makeRequest(url, options = {}) {
        try {
            const response = await fetch(url, {
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                },
                ...options
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
            }

            return await response.json();
        } catch (error) {
            console.error('API request failed:', error);
            throw error;
        }
    }

    // Guard an action on a previously-fetched temp file; shows an error if missing.
    requireTempFile(message = 'Please fetch data first') {
        if (!this.currentTempFile) {
            this.showError(message);
            return false;
        }
        return true;
    }

    // Run a backend action: open the progress modal, POST, and surface errors.
    // Progress and completion are delivered asynchronously via socket events.
    async runAction(url, { title = 'Processing...', body = null, errorLabel = 'complete action' } = {}) {
        try {
            this.showProgress(title);
            const options = { method: 'POST' };
            if (body) options.body = JSON.stringify(body);
            return await this.makeRequest(url, options);
        } catch (error) {
            this.hideProgress();
            this.showError(`Failed to ${errorLabel}: ${error.message}`);
            return null;
        }
    }

    // Playlist handling
    handlePlaylistFetched(data) {
        this.currentTempFile = data.temp_file;
        this.currentPlaylistName = data.playlist_name;
        this.currentPlaylistData = data.tracks;
        this.foundAlbums = [];  // Reset MB status
        this.currentPage = 1;

        // Show playlist results
        const resultsDiv = document.getElementById('playlist-results');
        const infoDiv = document.getElementById('playlist-info');

        if (resultsDiv && infoDiv) {
            infoDiv.innerHTML = `
                <div class="alert alert-success">
                    <h6><i class="fas fa-check-circle me-2"></i>Playlist Fetched Successfully!</h6>
                    <p class="mb-0"><strong>${data.playlist_name}</strong> - ${data.track_count} tracks</p>
                </div>
            `;

            this.renderTrackPage();
            this.bindPaginationEvents();

            resultsDiv.style.display = 'block';
            resultsDiv.scrollIntoView({ behavior: 'smooth' });
        }
    }

    // Render current page of tracks
    renderTrackPage() {
        const trackList = document.getElementById('track-list');
        const countDisplay = document.getElementById('track-count-display');
        const paginationInfo = document.getElementById('pagination-info');
        const prevPage = document.getElementById('prev-page');
        const nextPage = document.getElementById('next-page');

        if (!trackList || !this.currentPlaylistData) return;

        const totalTracks = this.currentPlaylistData.length;
        const totalPages = Math.ceil(totalTracks / this.tracksPerPage);
        const startIdx = (this.currentPage - 1) * this.tracksPerPage;
        const endIdx = Math.min(startIdx + this.tracksPerPage, totalTracks);
        const pageTracks = this.currentPlaylistData.slice(startIdx, endIdx);

        // Update count display
        if (countDisplay) {
            countDisplay.textContent = totalTracks;
        }

        // Update pagination info
        if (paginationInfo) {
            paginationInfo.textContent = `Page ${this.currentPage} of ${totalPages}`;
        }

        // Update pagination buttons
        if (prevPage) {
            prevPage.classList.toggle('disabled', this.currentPage <= 1);
        }
        if (nextPage) {
            nextPage.classList.toggle('disabled', this.currentPage >= totalPages);
        }

        // Render tracks
        trackList.innerHTML = '';
        pageTracks.forEach(track => {
            const row = document.createElement('tr');
            const mbStatus = this.isAlbumFound(track)
                ? '<i class="fas fa-check text-success" title="Found in MusicBrainz"></i>'
                : '<span class="text-muted">-</span>';
            row.innerHTML = `
                <td class="text-center">${mbStatus}</td>
                <td>${this.escapeHtml(track.track_name)}</td>
                <td>${this.escapeHtml(track.artist_name)}</td>
                <td>${this.escapeHtml(track.album_name)}</td>
            `;
            trackList.appendChild(row);
        });
    }

    // Check if a track's album was found in MusicBrainz
    isAlbumFound(track) {
        if (!this.foundAlbums.length) return false;
        const artistName = (track.artist_name || '').split(',')[0].toLowerCase().trim();
        const albumName = (track.album_name || '').toLowerCase().trim();
        return this.foundAlbums.some(a =>
            a.album === albumName ||
            (a.artist === artistName && a.album === albumName)
        );
    }

    // Bind pagination click events
    bindPaginationEvents() {
        const prevPage = document.getElementById('prev-page');
        const nextPage = document.getElementById('next-page');

        if (prevPage) {
            prevPage.onclick = (e) => {
                e.preventDefault();
                if (this.currentPage > 1) {
                    this.currentPage--;
                    this.renderTrackPage();
                }
            };
        }

        if (nextPage) {
            nextPage.onclick = (e) => {
                e.preventDefault();
                const totalPages = Math.ceil(this.currentPlaylistData.length / this.tracksPerPage);
                if (this.currentPage < totalPages) {
                    this.currentPage++;
                    this.renderTrackPage();
                }
            };
        }
    }

    // Update MB status after scan
    updateMBStatus(foundAlbums) {
        this.foundAlbums = foundAlbums || [];
        this.renderTrackPage();  // Re-render to show checkmarks
    }

    // Liked songs handling
    handleLikedSongsFetched(data) {
        this.currentTempFile = data.temp_file;
        this.currentLikedSongsData = data.tracks;

        // Show liked songs results
        const resultsDiv = document.getElementById('liked-songs-results');
        const infoDiv = document.getElementById('liked-songs-info');
        const trackList = document.getElementById('track-list-liked');

        if (resultsDiv && infoDiv && trackList) {
            infoDiv.innerHTML = `
                <div class="alert alert-success">
                    <h6><i class="fas fa-check-circle me-2"></i>Liked Songs Fetched Successfully!</h6>
                    <p class="mb-0"><strong>${data.track_count}</strong> liked songs retrieved</p>
                </div>
            `;

            // Populate track preview
            trackList.innerHTML = '';
            data.tracks.forEach(track => {
                const row = document.createElement('tr');
                const addedDate = new Date(track.added_at).toLocaleDateString();
                row.innerHTML = `
                    <td>${this.escapeHtml(track.track_name)}</td>
                    <td>${this.escapeHtml(track.artist_name)}</td>
                    <td>${this.escapeHtml(track.album_name)}</td>
                    <td>${addedDate}</td>
                `;
                trackList.appendChild(row);
            });

            resultsDiv.style.display = 'block';
            resultsDiv.scrollIntoView({ behavior: 'smooth' });
        }
    }

    // M3U generation handling
    handleM3UGenerated(data) {
        const downloadUrl = `/download/${encodeURIComponent(data.file_path)}`;
        this.showSuccess(
            'M3U playlist has been generated successfully!',
            downloadUrl
        );
    }

    // Lidarr completion handling
    handleLidarrComplete(data) {
        this.showSuccess(data.message);
    }

    // Download JSON function
    downloadJSON(data, filename) {
        const jsonString = JSON.stringify(data, null, 2);
        const blob = new Blob([jsonString], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = `${filename}_${new Date().toISOString().split('T')[0]}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        this.showSuccess(`JSON file "${a.download}" has been downloaded successfully!`);
    }

    // Utility functions
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    formatDuration(ms) {
        const minutes = Math.floor(ms / 60000);
        const seconds = ((ms % 60000) / 1000).toFixed(0);
        return `${minutes}:${seconds.padStart(2, '0')}`;
    }

    formatDate(dateString) {
        return new Date(dateString).toLocaleDateString();
    }

    // User profile loading
    async loadUserProfile() {
        const usernameElement = document.getElementById('username');
        const userDetailsElement = document.getElementById('user-details');
        
        // Only load if elements exist (user is authenticated)
        if (!usernameElement || !userDetailsElement) {
            return;
        }

        try {
            const profile = await this.makeRequest('/api/user-profile');
            
            // Update username in navbar
            usernameElement.textContent = profile.display_name || profile.id;
            
            // Update user details in dropdown
            const followerText = profile.followers > 0 ? `${profile.followers} followers` : 'No followers';
            userDetailsElement.innerHTML = `
                <i class="fab fa-spotify me-1"></i>${profile.id}<br>
                <small>${followerText}</small>
            `;
            
        } catch (error) {
            console.error('Failed to load user profile:', error);
            usernameElement.textContent = 'User';
            userDetailsElement.textContent = 'Profile unavailable';
        }
    }

    // Animation helpers
    fadeIn(element) {
        element.classList.add('fade-in');
        element.style.display = 'block';
    }

    slideIn(element) {
        element.classList.add('slide-in');
        element.style.display = 'block';
    }
}

// Initialize the app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.spotifyApp = new SpotifyMigrationApp();
});

// Export for use in other scripts
window.SpotifyMigrationApp = SpotifyMigrationApp;
