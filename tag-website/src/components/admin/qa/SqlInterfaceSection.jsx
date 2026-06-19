const SqlInterfaceSection = ({
  sqlSessionToken,
  sqlSessionExpires,
  logoutSqlSession,
  sqlPinModalOpen,
  setSqlPinModalOpen,
  sqlPin,
  setSqlPin,
  verifySqlPin,
  sqlPinError,
  sqlQuery,
  setSqlQuery,
  executeSqlQuery,
  sqlLoading,
  sqlError,
  setSqlError,
  sqlResults,
  setSqlResults,
  exportSqlResultsCSV,
  exportSqlResultsPDF,
  sqlHistory,
  sqlTemplates,
  sqlTemplatesExpanded,
  setSqlTemplatesExpanded,
}) => {
  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h2>SQL Interface</h2>
        {sqlSessionToken && (
          <div className="sql-session-info">
            <span className="sql-session-active">Session Active</span>
            <span className="sql-session-expires">
              Expires: {sqlSessionExpires?.toLocaleTimeString()}
            </span>
            <button onClick={logoutSqlSession} className="admin-btn admin-btn-danger">
              Lock
            </button>
          </div>
        )}
      </div>

      {!sqlSessionToken ? (
        <div className="sql-locked">
          <div className="sql-locked-icon">🔒</div>
          <h4>SQL Interface Locked</h4>
          <p>Enter the admin PIN to access the database.</p>
          <button onClick={() => setSqlPinModalOpen(true)} className="admin-btn admin-btn-primary">
            Unlock SQL Interface
          </button>
        </div>
      ) : (
        <div className="sql-interface">
          <div className="sql-readonly-notice" style={{
            padding: '8px 12px',
            marginBottom: '8px',
            background: '#f5f5f5',
            border: '1px solid #ddd',
            borderRadius: '4px',
            fontSize: '13px',
            color: '#555',
          }}>
            <strong>Read-only console.</strong> Only SELECT and WITH (CTE) queries are
            permitted. Writes go through inline <code>python3 -c</code> scripts.
          </div>

          <div className="sql-editor">
            <textarea
              value={sqlQuery}
              onChange={(e) => setSqlQuery(e.target.value)}
              placeholder="Enter your SELECT query here...&#10;&#10;Example: SELECT * FROM bookings LIMIT 10"
              className="sql-textarea"
              rows={8}
            />
            <div className="sql-editor-actions">
              <button
                onClick={() => executeSqlQuery()}
                disabled={sqlLoading || !sqlQuery.trim()}
                className="sql-run-btn"
              >
                {sqlLoading ? 'Executing...' : 'Run Query'}
              </button>
              <button
                onClick={() => {
                  setSqlQuery('')
                  setSqlResults(null)
                  setSqlError('')
                }}
                className="sql-clear-btn"
              >
                Clear
              </button>
            </div>
          </div>

          {sqlError && (
            <div className="sql-error">
              <strong>Error:</strong> {sqlError}
            </div>
          )}

          {sqlResults && (
            <div className="sql-results">
              <div className="sql-results-header">
                <span className="sql-results-meta">
                  {sqlResults.query_type === 'SELECT' ? (
                    <>
                      {sqlResults.row_count} row{sqlResults.row_count !== 1 ? 's' : ''} returned
                      {sqlResults.has_more && ' (limited to 500)'}
                    </>
                  ) : (
                    <>{sqlResults.affected_rows} row{sqlResults.affected_rows !== 1 ? 's' : ''} affected</>
                  )}
                  {' • '}{sqlResults.execution_time}s
                </span>
                {sqlResults.query_type === 'SELECT' && sqlResults.data && sqlResults.data.length > 0 && (
                  <div className="sql-export-buttons">
                    <button
                      className="sql-export-btn"
                      onClick={exportSqlResultsCSV}
                      title="Download as CSV"
                    >
                      CSV
                    </button>
                    <button
                      className="sql-export-btn"
                      onClick={exportSqlResultsPDF}
                      title="Print / Save as PDF"
                    >
                      PDF
                    </button>
                  </div>
                )}
              </div>

              {sqlResults.query_type === 'SELECT' && sqlResults.data && (
                <div className="sql-results-table-wrapper">
                  <table className="sql-results-table">
                    <thead>
                      <tr>
                        {sqlResults.columns.map((col, i) => (
                          <th key={i}>{col}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {sqlResults.data.map((row, rowIdx) => (
                        <tr key={rowIdx}>
                          {sqlResults.columns.map((col, colIdx) => (
                            <td key={colIdx}>
                              {row[col] === null ? (
                                <span className="sql-null">NULL</span>
                              ) : typeof row[col] === 'object' ? (
                                JSON.stringify(row[col])
                              ) : (
                                String(row[col])
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {sqlHistory.length > 0 && (
            <div className="sql-history">
              <h4>Recent Queries</h4>
              <ul>
                {sqlHistory.slice(0, 5).map((item, idx) => (
                  <li key={idx} onClick={() => setSqlQuery(item.query)}>
                    <code>{item.query.length > 60 ? item.query.substring(0, 60) + '...' : item.query}</code>
                    <span className="sql-history-meta">
                      {item.rowCount} rows • {item.timestamp.toLocaleTimeString()}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="sql-templates">
            <h4>Query Templates</h4>
            <div className="sql-templates-grid">
              {Object.entries(sqlTemplates).map(([category, templates]) => (
                <div key={category} className="sql-template-category">
                  <div
                    className={`sql-template-category-header ${sqlTemplatesExpanded[category] ? 'expanded' : ''}`}
                    onClick={() => setSqlTemplatesExpanded(prev => ({ ...prev, [category]: !prev[category] }))}
                  >
                    <span className="sql-template-category-icon">{sqlTemplatesExpanded[category] ? '▼' : '▶'}</span>
                    <span className="sql-template-category-name">{category}</span>
                    <span className="sql-template-count">{templates.length}</span>
                  </div>
                  {sqlTemplatesExpanded[category] && (
                    <div className="sql-template-list">
                      {templates.map((template, idx) => (
                        <div
                          key={idx}
                          className="sql-template-item"
                          onClick={() => setSqlQuery(template.query)}
                        >
                          <div className="sql-template-name">{template.name}</div>
                          <div className="sql-template-note">{template.note}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="sql-security-notice">
            <strong>Security:</strong> All queries are logged to the audit_logs table.
            Console is read-only — only SELECT and WITH (CTE) queries reach the
            database; everything else (INSERT, UPDATE, DELETE, DROP, TRUNCATE,
            ALTER, CREATE, GRANT, etc.) is blocked and audited.
            The database transaction is set READ ONLY before each query, so writes
            nested inside CTEs and SELECT...INTO are also rejected at the DB layer.
          </div>
        </div>
      )}

      {sqlPinModalOpen && (
        <div className="admin-modal-overlay" onClick={() => setSqlPinModalOpen(false)}>
          <div className="admin-modal sql-pin-modal" onClick={(e) => e.stopPropagation()}>
            <div className="admin-modal-header">
              <h3>🔐 SQL Interface Authentication</h3>
              <button onClick={() => setSqlPinModalOpen(false)} className="admin-modal-close">&times;</button>
            </div>
            <div className="admin-modal-body">
              <p>Enter the admin PIN to unlock the SQL interface.</p>
              <p className="sql-pin-notice">This session will expire after 2 hours of inactivity.</p>
              <input
                type="password"
                value={sqlPin}
                onChange={(e) => setSqlPin(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && verifySqlPin()}
                placeholder="Enter PIN"
                className="admin-input sql-pin-input"
                autoFocus
              />
              {sqlPinError && <p className="sql-pin-error">{sqlPinError}</p>}
            </div>
            <div className="admin-modal-footer">
              <button onClick={() => setSqlPinModalOpen(false)} className="admin-btn">Cancel</button>
              <button onClick={verifySqlPin} className="admin-btn admin-btn-primary">Unlock</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default SqlInterfaceSection
