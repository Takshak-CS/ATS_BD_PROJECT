import { startTransition, useDeferredValue, useEffect, useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const INGESTION_API_BASE_URL =
  import.meta.env.VITE_INGESTION_API_BASE_URL ?? "http://localhost:8010";

async function fetchJson(path) {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with status ${response.status}`);
  }
  return response.json();
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "0.0%";
  }
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function formatJobSubtitle(job) {
  return [job.location, job.employment_type, job.experience_required].filter(Boolean).join(" • ");
}

function formatBytes(value) {
  if (!value) {
    return "0 B";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export default function App() {
  const [jobs, setJobs] = useState([]);
  const [jobQuery, setJobQuery] = useState("");
  const [selectedJobId, setSelectedJobId] = useState(null);
  const [selectedJob, setSelectedJob] = useState(null);
  const [rankings, setRankings] = useState([]);
  const [selectedResumeId, setSelectedResumeId] = useState(null);
  const [candidateDetail, setCandidateDetail] = useState(null);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [rankingsLoading, setRankingsLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadResumeId, setUploadResumeId] = useState("");
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadSubmitting, setUploadSubmitting] = useState(false);
  const [uploadInputKey, setUploadInputKey] = useState(0);
  const [error, setError] = useState("");

  const deferredJobQuery = useDeferredValue(jobQuery);
  const normalizedQuery = deferredJobQuery.trim().toLowerCase();

  const filteredJobs = jobs.filter((job) => {
    if (!normalizedQuery) {
      return true;
    }
    const haystack = [job.job_title, job.location, job.job_id].filter(Boolean).join(" ").toLowerCase();
    return haystack.includes(normalizedQuery);
  });

  useEffect(() => {
    let ignore = false;
    setJobsLoading(true);
    fetchJson("/jobs")
      .then((payload) => {
        if (ignore) {
          return;
        }
        const nextJobs = payload.jobs ?? [];
        setJobs(nextJobs);
        startTransition(() => {
          setSelectedJobId(nextJobs[0]?.job_id ?? null);
        });
        setError("");
      })
      .catch((err) => {
        if (!ignore) {
          setError(`Unable to load jobs from ${API_BASE_URL}: ${err.message}`);
        }
      })
      .finally(() => {
        if (!ignore) {
          setJobsLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedJobId) {
      setRankings([]);
      setSelectedJob(null);
      return;
    }

    let ignore = false;
    setRankingsLoading(true);
    setCandidateDetail(null);
    fetchJson(`/jobs/${selectedJobId}/rankings`)
      .then((payload) => {
        if (ignore) {
          return;
        }
        const nextRankings = payload.rankings ?? [];
        setSelectedJob(payload.job ?? null);
        setRankings(nextRankings);
        startTransition(() => {
          setSelectedResumeId(nextRankings[0]?.resume_id ?? null);
        });
        setError("");
      })
      .catch((err) => {
        if (!ignore) {
          setError(`Unable to load rankings for ${selectedJobId}: ${err.message}`);
        }
      })
      .finally(() => {
        if (!ignore) {
          setRankingsLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [selectedJobId]);

  useEffect(() => {
    if (!selectedJobId || !selectedResumeId) {
      setCandidateDetail(null);
      return;
    }

    let ignore = false;
    setDetailLoading(true);
    fetchJson(`/jobs/${selectedJobId}/rankings/${selectedResumeId}`)
      .then((payload) => {
        if (!ignore) {
          setCandidateDetail(payload);
          setError("");
        }
      })
      .catch((err) => {
        if (!ignore) {
          setError(`Unable to load candidate detail for ${selectedResumeId}: ${err.message}`);
        }
      })
      .finally(() => {
        if (!ignore) {
          setDetailLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [selectedJobId, selectedResumeId]);

  async function handleUploadSubmit(event) {
    event.preventDefault();
    if (!uploadFile) {
      setUploadMessage("Choose a PDF, DOCX, or TXT resume before uploading.");
      return;
    }

    setUploadSubmitting(true);
    try {
      const headers = {
        "content-type": uploadFile.type || "application/octet-stream",
        "x-filename": uploadFile.name,
      };
      if (uploadResumeId.trim()) {
        headers["x-resume-id"] = uploadResumeId.trim();
      }

      const response = await fetch(`${INGESTION_API_BASE_URL}/uploads/resumes`, {
        method: "POST",
        headers,
        body: uploadFile,
      });
      const rawBody = await response.text();
      let payload = {};
      if (rawBody) {
        try {
          payload = JSON.parse(rawBody);
        } catch {
          payload = { detail: rawBody };
        }
      }
      if (!response.ok) {
        throw new Error(payload.detail || `Upload failed with status ${response.status}`);
      }

      setUploadMessage(
        `Uploaded ${payload.source_filename} as ${payload.resume_id}. ` +
          `${formatBytes(payload.file_size_bytes)} staged and event published.`,
      );
      setUploadFile(null);
      setUploadResumeId("");
      setUploadInputKey((value) => value + 1);
      setError("");
    } catch (err) {
      setUploadMessage("");
      setError(`Unable to upload resume to ${INGESTION_API_BASE_URL}: ${err.message}`);
    } finally {
      setUploadSubmitting(false);
    }
  }

  return (
    <div className="app-shell">
      <div className="hero-strip">
        <div>
          <p className="eyebrow">ATS Recruiter Console</p>
          <h1>Semantic resume screening, retrieval, and explainable ranking.</h1>
          <p className="hero-copy">
            Browse ingested jobs, inspect ranked candidates, and open full parser-backed
            profiles without leaving the pipeline workspace.
          </p>
        </div>
        <div className="upload-card">
          <p className="card-label">Resume Upload</p>
          <h2>Push a new resume into the event pipeline.</h2>
          <p>
            Uploads are staged locally for the parser consumer and immediately publish a
            <code> resume.uploaded </code>
            event.
          </p>
          <form className="upload-form" onSubmit={handleUploadSubmit}>
            <label className="upload-field">
              <span className="card-label">Resume File</span>
              <input
                accept=".pdf,.docx,.txt"
                className="upload-file-input"
                key={uploadInputKey}
                onChange={(event) => {
                  setUploadFile(event.target.files?.[0] ?? null);
                  setUploadMessage("");
                }}
                type="file"
              />
            </label>

            <label className="upload-field">
              <span className="card-label">Optional Resume ID</span>
              <input
                className="upload-input"
                onChange={(event) => setUploadResumeId(event.target.value)}
                placeholder="Defaults to the filename stem"
                type="text"
                value={uploadResumeId}
              />
            </label>

            <button disabled={uploadSubmitting} type="submit">
              {uploadSubmitting ? "Uploading..." : "Upload Resume"}
            </button>
          </form>
          <p className="upload-hint">
            Processing still depends on the parser, embedding, and ranking consumers running
            in separate terminals.
          </p>
          {uploadMessage ? <div className="status-banner success-banner">{uploadMessage}</div> : null}
        </div>
      </div>

      {error ? <div className="status-banner error-banner">{error}</div> : null}

      <div className="workspace-grid">
        <section className="panel jobs-panel">
          <div className="panel-header">
            <div>
              <p className="panel-kicker">Job Descriptions</p>
              <h2>{jobsLoading ? "Loading jobs..." : `${filteredJobs.length} jobs ready`}</h2>
            </div>
            <input
              aria-label="Search jobs"
              className="search-input"
              onChange={(event) => setJobQuery(event.target.value)}
              placeholder="Search title, location, or job id"
              type="search"
              value={jobQuery}
            />
          </div>
          <div className="job-list">
            {filteredJobs.map((job) => (
              <button
                className={`job-card ${job.job_id === selectedJobId ? "active" : ""}`}
                key={job.job_id}
                onClick={() => setSelectedJobId(job.job_id)}
                type="button"
              >
                <span className="job-card-title">{job.job_title}</span>
                <span className="job-card-meta">{formatJobSubtitle(job) || job.job_id}</span>
              </button>
            ))}
            {!jobsLoading && !filteredJobs.length ? (
              <div className="empty-state">No job descriptions match the current filter.</div>
            ) : null}
          </div>
        </section>

        <section className="panel rankings-panel">
          <div className="panel-header">
            <div>
              <p className="panel-kicker">Ranked Candidates</p>
              <h2>{selectedJob?.job_title ?? "Select a job"}</h2>
            </div>
            <span className="pill">
              {rankingsLoading ? "Refreshing..." : `${rankings.length} ranked candidates`}
            </span>
          </div>

          <div className="ranking-list">
            {rankings.map((candidate) => (
              <button
                className={`ranking-card ${candidate.resume_id === selectedResumeId ? "active" : ""}`}
                key={candidate.resume_id}
                onClick={() => setSelectedResumeId(candidate.resume_id)}
                type="button"
              >
                <div className="ranking-topline">
                  <span className="rank-badge">#{candidate.ranking_rank}</span>
                  <span className="candidate-name">{candidate.name || candidate.resume_id}</span>
                  <span className="score-pill">{formatPercent(candidate.final_score)}</span>
                </div>
                <div className="candidate-meta">
                  <span>{candidate.email || "Email unavailable"}</span>
                  <span>{candidate.experience_count ?? 0} exp entries</span>
                  <span>{candidate.warning_count ?? 0} parser warnings</span>
                </div>
              </button>
            ))}
            {!rankingsLoading && !rankings.length ? (
              <div className="empty-state">No rankings available for this job yet.</div>
            ) : null}
          </div>
        </section>

        <section className="panel detail-panel">
          <div className="panel-header">
            <div>
              <p className="panel-kicker">Candidate Detail</p>
              <h2>{candidateDetail?.candidate_profile?.name ?? "Select a candidate"}</h2>
            </div>
          </div>

          {detailLoading ? <div className="empty-state">Loading candidate detail...</div> : null}

          {!detailLoading && candidateDetail ? (
            <div className="detail-stack">
              <div className="detail-block">
                <h3>Score Breakdown</h3>
                <div className="metric-grid">
                  {Object.entries(candidateDetail.ranking.score_breakdown ?? {}).map(([label, value]) => (
                    <div className="metric-card" key={label}>
                      <span className="metric-label">{label.replaceAll("_", " ")}</span>
                      <strong>{formatPercent(value)}</strong>
                    </div>
                  ))}
                </div>
              </div>

              <div className="detail-block">
                <h3>Candidate Snapshot</h3>
                <div className="snapshot-grid">
                  <div>
                    <span className="snapshot-label">Email</span>
                    <p>{candidateDetail.candidate_profile.email || "Unavailable"}</p>
                  </div>
                  <div>
                    <span className="snapshot-label">Phone</span>
                    <p>{candidateDetail.candidate_profile.phone || "Unavailable"}</p>
                  </div>
                  <div>
                    <span className="snapshot-label">Resume ID</span>
                    <p>{candidateDetail.candidate_profile.resume_id}</p>
                  </div>
                  <div>
                    <span className="snapshot-label">Parser Warnings</span>
                    <p>{candidateDetail.candidate_profile.warning_count}</p>
                  </div>
                </div>
              </div>

              <div className="detail-block">
                <h3>Skills</h3>
                <div className="skill-cloud">
                  {(candidateDetail.candidate_profile.skills ?? []).map((skill) => (
                    <span className="skill-chip" key={skill}>
                      {skill}
                    </span>
                  ))}
                  {!candidateDetail.candidate_profile.skills?.length ? (
                    <span className="empty-inline">No parsed skills available.</span>
                  ) : null}
                </div>
              </div>

              <div className="detail-block">
                <h3>Education</h3>
                <ul className="detail-list">
                  {((candidateDetail.candidate_profile.profile_json?.education) ?? []).map((entry, index) => (
                    <li key={`education-${index}`}>{entry.raw_text}</li>
                  ))}
                  {!candidateDetail.candidate_profile.profile_json?.education?.length ? (
                    <li className="empty-inline">No education entries available.</li>
                  ) : null}
                </ul>
              </div>

              <div className="detail-block">
                <h3>Experience</h3>
                <ul className="detail-list">
                  {((candidateDetail.candidate_profile.profile_json?.experience) ?? []).map((entry, index) => (
                    <li key={`experience-${index}`}>{entry.raw_text}</li>
                  ))}
                  {!candidateDetail.candidate_profile.profile_json?.experience?.length ? (
                    <li className="empty-inline">No experience entries available.</li>
                  ) : null}
                </ul>
              </div>

              <div className="detail-block">
                <h3>Projects</h3>
                <ul className="detail-list">
                  {((candidateDetail.candidate_profile.profile_json?.projects) ?? []).map((entry, index) => (
                    <li key={`project-${index}`}>{entry.raw_text}</li>
                  ))}
                  {!candidateDetail.candidate_profile.profile_json?.projects?.length ? (
                    <li className="empty-inline">No projects available.</li>
                  ) : null}
                </ul>
              </div>
            </div>
          ) : null}

          {!detailLoading && !candidateDetail ? (
            <div className="empty-state">Choose a candidate to inspect their full parsed profile.</div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
