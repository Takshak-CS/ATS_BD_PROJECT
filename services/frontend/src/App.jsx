import {
  startTransition,
  useDeferredValue,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  BriefcaseBusiness,
  Trophy,
  UserCircle2,
  Upload,
  GraduationCap,
  FolderGit2,
  Briefcase,
  Search,
  Activity,
} from "lucide-react";

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

function scoreTier(value) {
  const pct = Number(value) || 0;
  if (pct >= 0.75) return "high";
  if (pct >= 0.5) return "mid";
  return "low";
}

function getInitials(name, fallback) {
  const source = (name || fallback || "").trim();
  if (!source) return "—";
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

function ScoreBar({ value }) {
  const pct = Math.max(0, Math.min(100, (Number(value) || 0) * 100));
  const tier = scoreTier(value);
  return (
    <div className={`score-bar tier-${tier}`}>
      <div className="score-bar-track">
        <div className="score-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="score-bar-label">{formatPercent(value)}</span>
    </div>
  );
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
  const [detailError, setDetailError] = useState("");
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadResumeId, setUploadResumeId] = useState("");
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadSubmitting, setUploadSubmitting] = useState(false);
  const [uploadInputKey, setUploadInputKey] = useState(0);
  const [error, setError] = useState("");
  const [isUploadOpen, setIsUploadOpen] = useState(false);

  // Pagination Window Constraints to safeguard DOM rendering performance
  const [visibleCount, setVisibleCount] = useState(50);

  const uploadDialogRef = useRef(null);

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
    setSelectedResumeId(null);
    setVisibleCount(50); // Reset visible window context when switching job categories
    
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
  console.log("========== DETAIL EFFECT ==========");
  console.log("selectedJobId:", selectedJobId);
  console.log("selectedResumeId:", selectedResumeId);

  if (!selectedJobId || !selectedResumeId) {
    setCandidateDetail(null);
    setDetailError("");
    return;
  }

  let ignore = false;
  setDetailLoading(true);
  setDetailError("");

  fetchJson(`/jobs/${selectedJobId}/rankings/${selectedResumeId}`)
    .then((payload) => {
      if (!ignore) {
        setCandidateDetail(payload);
        setDetailError("");
      }
    })
    .catch((err) => {
      if (!ignore) {
        setCandidateDetail(null);
        setDetailError(
          `This candidate's detail record couldn't be loaded (${err.message}).`
        );
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
  useEffect(() => {
    if (!isUploadOpen) {
      return;
    }
    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setIsUploadOpen(false);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isUploadOpen]);

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

  const scoreEntries = Object.entries(candidateDetail?.ranking?.score_breakdown ?? {});
  const profile = candidateDetail?.candidate_profile;

  // Compute sliced subset array dynamically
  const displayedRankings = rankings.slice(0, visibleCount);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">
  	    <Activity size={24} strokeWidth={2.4} />
	  </div>
          <div className="brand-text">
            <span className="brand-name">Recruiter Console</span>
            <span className="brand-sub">Semantic screening &amp; ranking pipeline</span>
          </div>
        </div>
        <div className="topbar-actions">
          <span className="env-chip">
            <span className="env-dot" aria-hidden="true" />
            Pipeline connected
          </span>
          <button
            className="btn-primary"
            onClick={() => setIsUploadOpen(true)}
            type="button"
          >
            <>
  	     <Upload size={18} />
  	     Upload Resume
           </>
          </button>
        </div>
      </header>

      {error ? (
        <div className="status-banner error-banner" role="alert">
          <strong>Something needs attention.</strong> {error}
        </div>
      ) : null}

      <main className="workspace-grid">
        <section className="panel jobs-panel">
          <div className="panel-header">
            <div>
              <p className="panel-kicker">
  		<BriefcaseBusiness size={14} />
  		Job Descriptions
	      </p>
              <h2>{jobsLoading ? "Loading jobs…" : `${filteredJobs.length} open roles`}</h2>
            </div>
          </div>
          <div className="search-wrapper">
  	    <Search size={18} className="search-icon" />

  	    <input
            aria-label="Search jobs"
            className="search-input"
            onChange={(event) => setJobQuery(event.target.value)}
            placeholder="Search title, location, or job ID"
            type="search"
            value={jobQuery}
          />
          </div>
          <div className="job-list">
            {filteredJobs.map((job) => (
              <button
                className={`job-card ${job.job_id === selectedJobId ? "active" : ""}`}
                key={job.job_id}
                onClick={() => {
    		    setSelectedResumeId(null);
    		    setSelectedJobId(job.job_id);
		}}
                type="button"
              >
                <span className="job-card-title">{job.job_title}</span>
                <span className="job-card-meta">{formatJobSubtitle(job) || job.job_id}</span>
              </button>
            ))}
            {!jobsLoading && !filteredJobs.length ? (
              <div className="empty-state">No job descriptions match this search.</div>
            ) : null}
          </div>
        </section>

        <section className="panel rankings-panel">
          <div className="panel-header">
            <div>
              <p className="panel-kicker">
  		<Trophy size={14} />
  		Ranked Candidates
	     </p>
              <h2>{selectedJob?.job_title ?? "Select a job"}</h2>
            </div>
            <span className="count-chip">
              {rankingsLoading ? "Refreshing…" : `${rankings.length} candidates`}
            </span>
          </div>

          <div className="ranking-list">
            {displayedRankings.map((candidate) => (
              <button
                className={`ranking-card ${candidate.resume_id === selectedResumeId ? "active" : ""}`}
                key={candidate.resume_id}
                onClick={() => setSelectedResumeId(candidate.resume_id)}
                type="button"
              >
                <span className="rank-badge">{candidate.ranking_rank}</span>
                <span className="ranking-main">
                  <span className="ranking-topline">
                    <span className="candidate-name">{candidate.name || candidate.resume_id}</span>
                  </span>
                  <span className="candidate-meta">
                    <span>{candidate.email || "Email unavailable"}</span>
                    <span className="meta-dot" aria-hidden="true" />
                    <span>{candidate.experience_count ?? 0} exp entries</span>
                    <span className="meta-dot" aria-hidden="true" />
                    <span>{candidate.warning_count ?? 0} warnings</span>
                  </span>
                  <ScoreBar value={candidate.final_score} />
                </span>
              </button>
            ))}

            {/* Seamless Pagination Trigger Control */}
            {!rankingsLoading && rankings.length > visibleCount ? (
              <button
                type="button"
                className="ranking-card"
                style={{
                  justifyContent: "center",
                  fontWeight: "600",
                  color: "var(--accent, #2563eb)",
                  border: "1px dashed #e2e8f0",
                  textAlign: "center",
                  padding: "16px"
                }}
                onClick={() => setVisibleCount((prev) => prev + 50)}
              >
                Load Next 50 Candidates ({rankings.length - visibleCount} remaining)
              </button>
            ) : null}

            {!rankingsLoading && !rankings.length ? (
              <div className="empty-state">No rankings available for this job yet.</div>
            ) : null}
          </div>
        </section>

        <section className="panel detail-panel">
          {detailLoading ? <div className="empty-state">Loading candidate detail…</div> : null}

          {!detailLoading && detailError ? (
            <div className="detail-error-state">
              <span className="detail-error-icon" aria-hidden="true">!</span>
              <div>
                <p className="detail-error-title">Couldn't load this candidate</p>
                <p className="detail-error-copy">
                  Their ranking summary loaded, but the full profile record is missing or out of
                  sync on the backend. Try another candidate, or re-run the ranking job for this
                  resume.
                </p>
              </div>
            </div>
          ) : null}

          {!detailLoading && !detailError && candidateDetail ? (
            <div className="detail-stack">
              <div className="detail-header">
                <span className="avatar">{getInitials(profile?.name, profile?.resume_id)}</span>
                <div className="detail-header-text">
                  <h2>{profile?.name ?? "Unnamed candidate"}</h2>
                  <span className="detail-header-meta">
                    {profile?.email || "Email unavailable"}
                    {profile?.phone ? ` · ${profile.phone}` : ""}
                  </span>
                </div>
                <ScoreBar value={candidateDetail?.ranking?.final_score} />
              </div>

              <div className="detail-block">
                <h3>
  		  <Activity size={18} />
  		   Score Breakdown
		</h3>
                <div className="metric-grid">
                  {scoreEntries.map(([label, value]) => (
                    <div className="metric-card" key={label}>
                      <span className="metric-label">{label.replaceAll("_", " ")}</span>
                      <ScoreBar value={value} />
                    </div>
                  ))}
                  {!scoreEntries.length ? (
                    <span className="empty-inline">No score breakdown available.</span>
                  ) : null}
                </div>
              </div>

              <div className="detail-block">
                <h3>
  		  <UserCircle2 size={18} />
  		   Candidate Snapshot
		</h3>
                <div className="snapshot-grid">
                  <div>
                    <span className="snapshot-label">Resume ID</span>
                    <p className="mono">{profile?.resume_id}</p>
                  </div>
                  <div>
                    <span className="snapshot-label">Parser warnings</span>
                    <p>{profile?.warning_count}</p>
                  </div>
                </div>
              </div>

              <div className="detail-block">
                <h3>
  		  <UserCircle2 size={18} />
  		   Skills
		</h3>
                <div className="skill-cloud">
                  {(profile?.skills ?? []).map((skill) => (
                    <span className="skill-chip" key={skill}>
                      {skill}
                    </span>
                  ))}
                  {!profile?.skills?.length ? (
                    <span className="empty-inline">No parsed skills available.</span>
                  ) : null}
                </div>
              </div>

              <div className="detail-block">
                <h3>
  		  <GraduationCap size={18} />
  		  Education
		</h3>
                <ul className="detail-list">
                  {(profile?.profile_json?.education ?? []).map((entry, index) => (
                    <li key={`education-${index}`}>{entry.raw_text}</li>
                  ))}
                  {!profile?.profile_json?.education?.length ? (
                    <li className="empty-inline">No education entries available.</li>
                  ) : null}
                </ul>
              </div>

              <div className="detail-block">
                <h3>
  		  <Briefcase size={18} />
  	          Experience
		</h3>
                <ul className="detail-list">
                  {(profile?.profile_json?.experience ?? []).map((entry, index) => (
                    <li key={`experience-${index}`}>{entry.raw_text}</li>
                  ))}
                  {!profile?.profile_json?.experience?.length ? (
                    <li className="empty-inline">No experience entries available.</li>
                  ) : null}
                </ul>
              </div>

              <div className="detail-block">
                <h3>
  		  <FolderGit2 size={18} />
  		 Projects
		</h3>
                <ul className="detail-list">
                  {(profile?.profile_json?.projects ?? []).map((entry, index) => (
                    <li key={`project-${index}`}>{entry.raw_text}</li>
                  ))}
                  {!profile?.profile_json?.projects?.length ? (
                    <li className="empty-inline">No projects available.</li>
                  ) : null}
                </ul>
              </div>
            </div>
          ) : null}

          {!detailLoading && !detailError && !candidateDetail ? (
            <div className="empty-state">Choose a candidate to inspect their full parsed profile.</div>
          ) : null}
        </section>
      </main>

      {isUploadOpen ? (
        <div
          className="modal-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setIsUploadOpen(false);
            }
          }}
        >
          <div className="modal" ref={uploadDialogRef} role="dialog" aria-modal="true" aria-label="Upload resume">
            <div className="modal-header">
              <div>
                <p className="panel-kicker">
  		   <Upload size={14} />
  		   Resume Upload
		</p>
                <h2>Add a resume to the pipeline</h2>
              </div>
              <button
                aria-label="Close"
                className="modal-close"
                onClick={() => setIsUploadOpen(false)}
                type="button"
              >
                ×
              </button>
            </div>
            <p className="modal-copy">
              The file is staged for the parser consumer and immediately publishes a
              <code> resume.uploaded </code>
              event.
            </p>
            <form className="upload-form" onSubmit={handleUploadSubmit}>
              <label className="upload-field">
                <span className="field-label">Resume file</span>
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
                <span className="field-label">Resume ID (optional)</span>
                <input
                  className="upload-input"
                  onChange={(event) => setUploadResumeId(event.target.value)}
                  placeholder="Defaults to the filename"
                  type="text"
                  value={uploadResumeId}
                />
              </label>

              <button className="btn-primary btn-block" disabled={uploadSubmitting} type="submit">
                {uploadSubmitting ? "Uploading…" : "Upload resume"}
              </button>
            </form>
            <p className="upload-hint">
              Processing depends on the parser, embedding, and ranking consumers running separately.
            </p>
            {uploadMessage ? <div className="status-banner success-banner">{uploadMessage}</div> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
