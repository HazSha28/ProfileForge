/**
 * pipeline.js
 * -----------
 * Client-side SSE (Server-Sent Events) handler for pipeline progress.
 * Connects to /api/process/stream and updates the UI in real-time.
 */

class PipelineProgress {
  constructor() {
    this.eventSource = null;
    this.stages = ['parse', 'normalize', 'merge', 'confidence', 'validate', 'project'];
    this.currentStage = null;
    this.profileData = null;
  }

  /**
   * Start the SSE connection and begin processing.
   * @param {FormData} formData - The form data with CSV and resume files
   */
  start(formData) {
    // Navigate to processing page
    window.location.href = '/processing';
    
    // Store form data in sessionStorage for the processing page to pick up
    const files = {};
    formData.forEach((value, key) => {
      if (value instanceof File) {
        files[key] = {
          name: value.name,
          size: value.size,
          type: value.type
        };
      }
    });
    sessionStorage.setItem('pipeline_files', JSON.stringify(files));
    sessionStorage.setItem('pipeline_config', formData.get('config') || '');
    sessionStorage.setItem('pipeline_links', formData.get('platform_links') || '');
  }

  /**
   * Initialize the processing page and connect to SSE stream.
   * This is called when the processing page loads.
   */
  initProcessingPage() {
    const formDataStr = sessionStorage.getItem('pipeline_formdata');
    const config = sessionStorage.getItem('pipeline_config') || '';
    const links = sessionStorage.getItem('pipeline_links') || '';

    if (!formDataStr) {
      this.showError('Missing form data. Please upload files again.');
      return;
    }

    try {
      const formDataObj = JSON.parse(formDataStr);
      const formData = new FormData();

      // Convert base64 back to File objects
      const filePromises = [];
      
      for (const [key, fileData] of Object.entries(formDataObj)) {
        if (fileData.data && fileData.name) {
          const promise = fetch(fileData.data)
            .then(res => res.blob())
            .then(blob => {
              const file = new File([blob], fileData.name, { type: fileData.type });
              formData.append(key, file);
            });
          filePromises.push(promise);
        }
      }

      // Add config and links
      if (config) formData.append('config', config);
      if (links) formData.append('platform_links', links);

      // Wait for all files to be converted, then start the stream
      Promise.all(filePromises).then(() => {
        this.connectStream(formData);
      });
    } catch (e) {
      this.showError('Error processing form data. Please try again.');
    }
  }

  /**
   * Connect to the SSE stream and handle events.
   */
  connectStream(formData) {
    const url = `/api/process/stream`;
    
    // We can't use EventSource with POST, so we'll use fetch with streaming
    this.startStreamingUpload(url, formData);
  }

  /**
   * Start streaming upload using fetch API.
   */
  async startStreamingUpload(url, formData) {
    try {
      const response = await fetch(url, {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
        this.showError(err.detail || 'Processing failed.');
        return;
      }

      // Read SSE stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const events = buffer.split('\n\n');
        buffer = events.pop() || '';

        for (const event of events) {
          if (!event.trim()) continue;
          const lines = event.split('\n');
          let eventType = '', dataStr = '';
          for (const line of lines) {
            if (line.startsWith('event: ')) eventType = line.slice(7).trim();
            if (line.startsWith('data: ')) dataStr = line.slice(6).trim();
          }
          if (!dataStr) continue;
          const data = JSON.parse(dataStr);

          if (eventType === 'progress') {
            this.updateProgress(data);
          } else if (eventType === 'error') {
            this.showError(data.message);
            return;
          } else if (eventType === 'complete') {
            this.handleComplete(data);
          }
        }
      }
    } catch (err) {
      this.showError('Could not connect to the server.');
    }
  }

  /**
   * Update the progress UI based on SSE events.
   */
  updateProgress(data) {
    const { stage, status, progress } = data;

    // Update progress bar
    const progressFill = document.getElementById('progress-fill');
    const progressStatus = document.getElementById('progress-status');
    
    if (progressFill) {
      progressFill.style.width = `${progress}%`;
    }
    
    if (progressStatus) {
      const stageNames = {
        parse: 'Parsing Sources',
        normalize: 'Normalizing Data',
        merge: 'Merging Records',
        confidence: 'Scoring Confidence',
        validate: 'Validating Schema',
        project: 'Generating Profile'
      };
      progressStatus.textContent = `${stageNames[stage] || stage} — ${Math.round(progress)}%`;
    }

    // Update stage indicators
    const stageElement = document.getElementById(`stage-${stage}`);
    if (stageElement) {
      const statusIcon = stageElement.querySelector('.pf-stage__status');
      
      if (status === 'running') {
        stageElement.classList.add('pf-stage--running');
        stageElement.classList.remove('pf-stage--done');
        if (statusIcon) {
          statusIcon.innerHTML = `
            <svg class="pf-stage__spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
              <circle cx="12" cy="12" r="10" stroke-dasharray="60" stroke-dashoffset="40"/>
            </svg>
          `;
        }
      } else if (status === 'done') {
        stageElement.classList.remove('pf-stage--running');
        stageElement.classList.add('pf-stage--done');
        if (statusIcon) {
          statusIcon.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          `;
        }
      }
    }

    // Mark previous stages as done
    const stageIndex = this.stages.indexOf(stage);
    for (let i = 0; i < stageIndex; i++) {
      const prevStage = document.getElementById(`stage-${this.stages[i]}`);
      if (prevStage && !prevStage.classList.contains('pf-stage--done')) {
        prevStage.classList.add('pf-stage--done');
        const statusIcon = prevStage.querySelector('.pf-stage__status');
        if (statusIcon) {
          statusIcon.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          `;
        }
      }
    }
  }

  /**
   * Handle pipeline completion.
   */
  handleComplete(data) {
    this.profileData = data.profile;
    
    // Store profile data for the profile page
    sessionStorage.setItem('profile_data', JSON.stringify(data.profile));
    sessionStorage.setItem('profile_warnings', JSON.stringify(data.warnings || []));
    
    // Close SSE connection
    if (this.eventSource) {
      this.eventSource.close();
    }

    // Redirect to profile page after a short delay
    setTimeout(() => {
      window.location.href = '/profile';
    }, 500);
  }

  /**
   * Show error state.
   */
  showError(message) {
    const errorContainer = document.getElementById('error-container');
    const errorMessage = document.getElementById('error-message');
    const pipelineStages = document.querySelector('.pf-pipeline-stages');
    
    if (pipelineStages) {
      pipelineStages.style.display = 'none';
    }
    
    if (errorContainer) {
      errorContainer.style.display = 'flex';
    }
    
    if (errorMessage) {
      errorMessage.textContent = message;
    }
  }

  /**
   * Clean up resources.
   */
  destroy() {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    sessionStorage.removeItem('pipeline_files');
    sessionStorage.removeItem('pipeline_config');
    sessionStorage.removeItem('pipeline_links');
  }
}

// Initialize on processing page load
document.addEventListener('DOMContentLoaded', () => {
  if (window.location.pathname === '/processing') {
    const pipeline = new PipelineProgress();
    pipeline.initProcessingPage();
  }
});
