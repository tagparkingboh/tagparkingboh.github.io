import { Fragment } from 'react'

  const MessagesSection = ({
  fetchSmsMessages,
  fetchSmsStats,
  loadingMessages,
  refreshSmsStatuses,
  setShowSendSmsModal,
  messagesMessage,
  smsStats,
  messagesSubTab,
  setMessagesSubTab,
  setSelectedThread,
  fetchSmsThreads,
  smsThreads,
  selectedThreads,
  toggleSelectAll,
  loadingThreads,
  selectedThread,
  selectThread,
  toggleThreadSelection,
  formatPhoneForDisplay,
  fetchConversation,
  loadingConversation,
  deleteThread,
  threadMessages,
  conversationEndRef,
  replyContent,
  setReplyContent,
  sendReply,
  sendingReply,
  setSmsDirectionFilter,
  setSmsStatusFilter,
  smsStatusFilter,
  showSendSmsModal,
  getSmsStatusBadge,
  smsMessages,
  setExpandedMessageId,
  expandedMessageId,
  resendingMessageId,
  handleResendMessage,
  setMessageToDelete,
  deletingMessageId,
  handleDeleteMessage,
  loadingTemplates,
  smsTemplates,
  setShowCreateTemplateModal,
  setSendSmsForm,
  setEditingTemplate,
  setShowEditTemplateModal,
  setTemplateToDelete,
  editingTemplate,
  savingTemplate,
  deletingTemplateId,
  templateToDelete,
  showEditTemplateModal,
  editTemplateTextareaRef,
  handleSaveTemplate,
  newTemplate,
  creatingTemplate,
  showCreateTemplateModal,
  newTemplateTextareaRef,
  setNewTemplate,
  sendSmsForm,
  smsBookingSearch,
  setSmsBookingSearch,
  searchingSmsBookings,
  smsBookingResults,
  setSmsBookingResults,
  searchBookingsForSms,
  selectBookingForSms,
  selectedSmsBooking,
  setSelectedSmsBooking,
  handleSaveDraft,
  savingDraft,
  editingDraft,
  handleSendSms,
  sendingSms,
  handleEditDraft,
  loadingDrafts,
  smsDrafts,
  sendingDraftId,
  handleSendDraft,
  handleDeleteDraft,
  deletingDraftId,
  clearSelectedBooking,
  smsVariables,
  insertSmsVariable,
  sendSmsTextareaRef,
  handleCreateTemplate,
  handleDeleteTemplate,
  messageToDelete,
  fetchSmsDrafts,
  bulkDeleteThreads,
  deletingThreads,
  setEditingDraft,
}) => {
  return (
<div className="admin-section">
  <div className="messages-header">
    <h2>SMS Messages</h2>
    <div className="messages-header-actions">
      <button
        className="btn-secondary"
        onClick={() => { fetchSmsMessages(); fetchSmsStats(); }}
        disabled={loadingMessages}
      >
        ↻ Refresh
      </button>
      <button
        className="btn-secondary"
        onClick={refreshSmsStatuses}
        disabled={loadingMessages}
        title="Check delivery status from SMS provider"
      >
        ✓ Update Statuses
      </button>
      <button
        className="btn-primary"
        onClick={() => setShowSendSmsModal(true)}
      >
        + Send SMS
      </button>
    </div>
  </div>

  {messagesMessage && (
    <div className={`messages-message ${messagesMessage.includes('Error') ? 'warning' : 'success'}`}>
      {messagesMessage}
    </div>
  )}

  {/* Stats Cards */}
  {smsStats && (
    <div className="sms-stats-grid">
      <div className="sms-stat-card">
        <div className="sms-stat-value">{smsStats.total_sent || 0}</div>
        <div className="sms-stat-label">Total Sent</div>
      </div>
      <div className="sms-stat-card">
        <div className="sms-stat-value">{smsStats.delivered || 0}</div>
        <div className="sms-stat-label">Delivered</div>
      </div>
      <div className="sms-stat-card">
        <div className="sms-stat-value">{smsStats.pending || 0}</div>
        <div className="sms-stat-label">Pending</div>
      </div>
      <div className="sms-stat-card">
        <div className="sms-stat-value">{smsStats.failed || 0}</div>
        <div className="sms-stat-label">Failed</div>
      </div>
      <div className="sms-stat-card">
        <div className="sms-stat-value">{smsStats.unread || 0}</div>
        <div className="sms-stat-label">Unread</div>
      </div>
      <div className="sms-stat-card">
        <div className="sms-stat-value">{smsStats.conversations || 0}</div>
        <div className="sms-stat-label">Conversations</div>
      </div>
    </div>
  )}

  {/* Sub-tabs */}
  <div className="messages-subtabs">
    <button
      className={`messages-subtab ${messagesSubTab === 'conversations' ? 'active' : ''}`}
      onClick={() => { setMessagesSubTab('conversations'); setSelectedThread(null); fetchSmsThreads() }}
    >
      Conversations {smsStats?.unread > 0 && <span className="unread-badge">{smsStats.unread}</span>}
    </button>
    <button
      className={`messages-subtab ${messagesSubTab === 'inbox' ? 'active' : ''}`}
      onClick={() => { setMessagesSubTab('inbox'); setSmsDirectionFilter('inbound') }}
    >
      Inbox
    </button>
    <button
      className={`messages-subtab ${messagesSubTab === 'sent' ? 'active' : ''}`}
      onClick={() => { setMessagesSubTab('sent'); setSmsDirectionFilter('outbound') }}
    >
      Sent
    </button>
    <button
      className={`messages-subtab ${messagesSubTab === 'templates' ? 'active' : ''}`}
      onClick={() => setMessagesSubTab('templates')}
    >
      Templates
    </button>
    <button
      className={`messages-subtab ${messagesSubTab === 'drafts' ? 'active' : ''}`}
      onClick={() => { setMessagesSubTab('drafts'); fetchSmsDrafts() }}
    >
      Drafts {smsDrafts.length > 0 && <span className="draft-count">({smsDrafts.length})</span>}
    </button>
  </div>

  {/* Filters for Inbox/Sent */}
  {(messagesSubTab === 'inbox' || messagesSubTab === 'sent') && (
    <div className="messages-filters">
      <div className="messages-filter-group">
        <label>Status:</label>
        <select
          value={smsStatusFilter}
          onChange={(e) => setSmsStatusFilter(e.target.value)}
        >
          <option value="all">All</option>
          <option value="pending">Pending</option>
          <option value="sent">Sent</option>
          <option value="delivered">Delivered</option>
          <option value="failed">Failed</option>
        </select>
      </div>
    </div>
  )}

  {/* Conversations View (Thread-based) */}
  {messagesSubTab === 'conversations' && (
    <div className="conversations-container">
      {/* Thread List (Left Panel) */}
      <div className="thread-list">
        <div className="thread-list-header">
          <div className="thread-list-title">
            <input
              type="checkbox"
              checked={smsThreads.length > 0 && selectedThreads.size === smsThreads.length}
              onChange={toggleSelectAll}
              title="Select all"
            />
            <h4>Conversations</h4>
          </div>
          <div className="thread-list-actions">
            {selectedThreads.size > 0 && (
              <button
                className="btn-icon danger"
                onClick={bulkDeleteThreads}
                disabled={deletingThreads}
                title={`Delete ${selectedThreads.size} selected`}
              >
                🗑 {selectedThreads.size}
              </button>
            )}
            <button
              className="btn-icon"
              onClick={fetchSmsThreads}
              disabled={loadingThreads}
              title="Refresh"
            >
              ↻
            </button>
          </div>
        </div>
        {loadingThreads ? (
          <div className="thread-loading">Loading...</div>
        ) : smsThreads.length === 0 ? (
          <div className="no-threads">No conversations yet</div>
        ) : (
          <div className="thread-items">
            {smsThreads.map((thread) => (
              <div
                key={thread.phone_number}
                className={`thread-item ${selectedThread?.phone_number === thread.phone_number ? 'selected' : ''} ${thread.unread_count > 0 ? 'unread' : ''} ${selectedThreads.has(thread.phone_number) ? 'checked' : ''}`}
                onClick={() => selectThread(thread)}
              >
                <input
                  type="checkbox"
                  checked={selectedThreads.has(thread.phone_number)}
                  onChange={(e) => toggleThreadSelection(thread.phone_number, e)}
                  onClick={(e) => e.stopPropagation()}
                  className="thread-checkbox"
                />
                <div className="thread-avatar">
                  {thread.customer?.name ? thread.customer.name.charAt(0).toUpperCase() : '?'}
                </div>
                <div className="thread-info">
                  <div className="thread-header">
                    <span className="thread-name">
                      {thread.customer?.name || formatPhoneForDisplay(thread.phone_number)}
                    </span>
                    <span className="thread-time">
                      {thread.last_activity ? new Date(thread.last_activity).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : ''}
                    </span>
                  </div>
                  <div className="thread-preview">
                    {thread.last_message?.direction === 'outbound' && <span className="preview-arrow">→ </span>}
                    {thread.last_message?.content || 'No messages'}
                  </div>
                  {thread.customer?.name && (
                    <div className="thread-phone">{formatPhoneForDisplay(thread.phone_number)}</div>
                  )}
                </div>
                {thread.unread_count > 0 && (
                  <div className="thread-unread-badge">{thread.unread_count}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Conversation Panel (Right Panel) */}
      <div className="conversation-panel">
        {!selectedThread ? (
          <div className="no-conversation-selected">
            <div className="empty-state-icon">💬</div>
            <p>Select a conversation to view messages</p>
          </div>
        ) : (
          <>
            {/* Conversation Header */}
            <div className="conversation-header">
              <div className="conversation-contact">
                <div className="contact-avatar">
                  {selectedThread.customer?.name ? selectedThread.customer.name.charAt(0).toUpperCase() : '?'}
                </div>
                <div className="contact-info">
                  <div className="contact-name">
                    {selectedThread.customer?.name || 'Unknown'}
                  </div>
                  <div className="contact-phone">{formatPhoneForDisplay(selectedThread.phone_number)}</div>
                </div>
              </div>
              <div className="conversation-actions">
                <button
                  className="btn-icon"
                  onClick={() => fetchConversation(selectedThread.phone_number)}
                  disabled={loadingConversation}
                  title="Refresh conversation"
                >
                  ↻
                </button>
                <button
                  className="btn-icon danger"
                  onClick={() => deleteThread(selectedThread.phone_number)}
                  title="Delete conversation"
                >
                  🗑
                </button>
              </div>
            </div>

            {/* Messages */}
            <div className="conversation-messages">
              {loadingConversation ? (
                <div className="conversation-loading">Loading messages...</div>
              ) : threadMessages.length === 0 ? (
                <div className="no-messages">No messages in this conversation</div>
              ) : (
                <>
                  {threadMessages.map((msg, index) => {
                    const showDate = index === 0 ||
                      new Date(msg.created_at).toDateString() !== new Date(threadMessages[index - 1].created_at).toDateString()
                    return (
                      <Fragment key={msg.id}>
                        {showDate && (
                          <div className="message-date-divider">
                            {new Date(msg.created_at).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })}
                          </div>
                        )}
                        <div className={`message-bubble ${msg.direction}`}>
                          <div className="message-content">{msg.content}</div>
                          <div className="message-meta">
                            <span className="message-time">
                              {new Date(msg.created_at).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
                            </span>
                            {msg.direction === 'outbound' && (
                              <span className={`message-status ${msg.status}`}>
                                {msg.status === 'delivered' ? '✓✓' : msg.status === 'sent' ? '✓' : msg.status === 'failed' ? '✗' : '○'}
                              </span>
                            )}
                            {msg.booking_reference && (
                              <span className="message-booking" title={`Booking: ${msg.booking_reference}`}>
                                📋
                              </span>
                            )}
                          </div>
                        </div>
                      </Fragment>
                    )
                  })}
                  <div ref={conversationEndRef} />
                </>
              )}
            </div>

            {/* Reply Input */}
            <div className="conversation-reply">
              <textarea
                value={replyContent}
                onChange={(e) => setReplyContent(e.target.value)}
                placeholder="Type a message..."
                rows={2}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    sendReply()
                  }
                }}
              />
              <button
                className="btn-send"
                onClick={sendReply}
                disabled={sendingReply || !replyContent.trim()}
              >
                {sendingReply ? '...' : 'Send'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )}

  {/* Messages List */}
  {(messagesSubTab === 'inbox' || messagesSubTab === 'sent') && (
    <div className="messages-list">
      {loadingMessages ? (
        <p className="loading-text">Loading messages...</p>
      ) : smsMessages.length === 0 ? (
        <p className="no-data">No messages found</p>
      ) : (
        <table className="admin-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Direction</th>
              <th>Phone</th>
              <th>Content</th>
              <th>Status</th>
              <th>Booking</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {smsMessages.map(msg => (
              <tr key={msg.id} className={expandedMessageId === msg.id ? 'expanded' : ''}>
                <td>{msg.created_at ? new Date(msg.created_at).toLocaleString('en-GB') : '-'}</td>
                <td>
                  <span className={`direction-badge ${msg.direction}`}>
                    {msg.direction === 'inbound' ? '← In' : '→ Out'}
                  </span>
                </td>
                <td>{formatPhoneForDisplay(msg.phone_number)}</td>
                <td className="message-content" onClick={() => setExpandedMessageId(expandedMessageId === msg.id ? null : msg.id)}>
                  {expandedMessageId === msg.id ? msg.content : (msg.content?.substring(0, 50) + (msg.content?.length > 50 ? '...' : ''))}
                </td>
                <td>
                  <span className={`status-badge ${getSmsStatusBadge(msg.status)}`}>
                    {msg.status}
                  </span>
                </td>
                <td>{msg.booking_reference || '-'}</td>
                <td>
                  <div style={{ display: 'flex', gap: '6px' }}>
                    {msg.direction === 'inbound' && (
                      <button
                        onClick={() => {
                          setSendSmsForm(prev => ({
                            ...prev,
                            phone: msg.phone_number || '',
                            customer_id: msg.customer_id || '',
                            content: ''
                          }))
                          setShowSendSmsModal(true)
                        }}
                        title="Reply to this message"
                        style={{ padding: '6px 12px', fontSize: '0.75rem', borderRadius: '20px', background: '#7c3aed', color: '#fff', border: 'none', cursor: 'pointer', fontWeight: '500' }}
                      >
                        Reply
                      </button>
                    )}
                    {msg.direction === 'outbound' && (
                      <button
                        onClick={() => handleResendMessage(msg.id)}
                        disabled={resendingMessageId === msg.id}
                        title="Resend this message"
                        style={{ padding: '6px 12px', fontSize: '0.75rem', borderRadius: '20px', background: '#e0e0e0', color: '#333', border: 'none', cursor: 'pointer', fontWeight: '500' }}
                      >
                        {resendingMessageId === msg.id ? '...' : 'Resend'}
                      </button>
                    )}
                    <button
                      onClick={() => setMessageToDelete(msg)}
                      disabled={deletingMessageId === msg.id}
                      title="Delete this message"
                      style={{ padding: '6px 12px', fontSize: '0.75rem', borderRadius: '20px', background: '#e0e0e0', color: '#333', border: 'none', cursor: 'pointer', fontWeight: '500' }}
                    >
                      {deletingMessageId === msg.id ? '...' : 'Delete'}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )}

  {/* Templates List */}
  {messagesSubTab === 'templates' && (
    <div className="templates-list">
      <div className="templates-header">
        <button
          className="btn-primary"
          onClick={() => setShowCreateTemplateModal(true)}
        >
          + Create Template
        </button>
      </div>
      {loadingTemplates ? (
        <p className="loading-text">Loading templates...</p>
      ) : smsTemplates.length === 0 ? (
        <p className="no-data">No templates found. Create one to get started!</p>
      ) : (
        <div className="templates-grid">
          {smsTemplates.map(template => (
            <div key={template.id} className={`template-card ${!template.is_active ? 'inactive' : ''}`}>
              <div className="template-header">
                <h4>{template.name}</h4>
                <div className="template-badges">
                  {template.is_automated && (
                    <span className="badge automated">Auto</span>
                  )}
                  {!template.is_active && (
                    <span className="badge inactive">Inactive</span>
                  )}
                </div>
              </div>
              {template.description && (
                <p className="template-description">{template.description}</p>
              )}
              <div className="template-content">
                <pre>{template.content}</pre>
              </div>
              {template.trigger_event && (
                <div className="template-trigger">
                  Trigger: <code>{template.trigger_event}</code>
                </div>
              )}
              <div className="template-actions">
                <button
                  className="btn-primary btn-sm"
                  onClick={() => {
                    setSendSmsForm(prev => ({ ...prev, content: template.content }))
                    setShowSendSmsModal(true)
                  }}
                >
                  Use
                </button>
                <button
                  className="btn-secondary btn-sm"
                  onClick={() => {
                    setEditingTemplate({ ...template })
                    setShowEditTemplateModal(true)
                  }}
                >
                  Edit
                </button>
                <button
                  className="btn-danger btn-sm"
                  onClick={() => setTemplateToDelete(template)}
                  disabled={deletingTemplateId === template.id}
                >
                  {deletingTemplateId === template.id ? 'Deleting...' : 'Delete'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Template Variables Reference */}
      <div className="template-variables-ref">
        <h4>Available Variables</h4>
        <div className="variables-list">
          <code>{'{{first_name}}'}</code>
          <code>{'{{last_name}}'}</code>
          <code>{'{{booking_reference}}'}</code>
          <code>{'{{dropoff_date}}'}</code>
          <code>{'{{dropoff_time}}'}</code>
          <code>{'{{pickup_date}}'}</code>
          <code>{'{{pickup_time}}'}</code>
          <code>{'{{destination}}'}</code>
          <code>{'{{vehicle_reg}}'}</code>
          <code>{'{{total_price}}'}</code>
          <code>{'{{days}}'}</code>
          <code>{'{{google_review_link}}'}</code>
        </div>
      </div>
    </div>
  )}

  {/* Drafts List */}
  {messagesSubTab === 'drafts' && (
    <div className="drafts-section">
      {loadingDrafts ? (
        <p className="loading-text">Loading drafts...</p>
      ) : smsDrafts.length === 0 ? (
        <p className="no-data">No drafts saved</p>
      ) : (
        <div className="drafts-list">
          {smsDrafts.map(draft => (
            <div key={draft.id} className="draft-card">
              <div className="draft-header">
                <span className="draft-phone">{draft.phone_number || '(No phone)'}</span>
                {draft.booking_reference && (
                  <span className="draft-booking">{draft.booking_reference}</span>
                )}
                <span className="draft-date">
                  {draft.created_at ? new Date(draft.created_at).toLocaleString('en-GB') : ''}
                </span>
              </div>
              <div className="draft-content">{draft.content || '(Empty)'}</div>
              <div className="draft-actions">
                <button
                  onClick={() => handleEditDraft(draft)}
                  style={{ padding: '6px 14px', fontSize: '0.75rem', borderRadius: '20px', background: '#e0e0e0', color: '#333', border: 'none', cursor: 'pointer', fontWeight: '600', marginRight: '8px' }}
                >
                  Edit
                </button>
                <button
                  onClick={() => handleSendDraft(draft.id)}
                  disabled={sendingDraftId === draft.id || !draft.phone_number || !draft.content}
                  style={{ padding: '6px 14px', fontSize: '0.75rem', borderRadius: '20px', background: '#f7b32b', color: '#1a1a2e', border: 'none', cursor: 'pointer', fontWeight: '600', marginRight: '8px' }}
                >
                  {sendingDraftId === draft.id ? 'Sending...' : 'Send'}
                </button>
                <button
                  onClick={() => handleDeleteDraft(draft.id)}
                  disabled={deletingDraftId === draft.id}
                  style={{ padding: '6px 14px', fontSize: '0.75rem', borderRadius: '20px', background: '#ff6b6b', color: '#fff', border: 'none', cursor: 'pointer', fontWeight: '600' }}
                >
                  {deletingDraftId === draft.id ? 'Deleting...' : 'Delete'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )}

  {/* Send SMS Modal */}
  {showSendSmsModal && (
    <div className="modal-overlay">
      <div className="modal-content modal-medium">
        <h3>{editingDraft ? 'Edit Draft' : 'Send SMS'}</h3>
        <div className="modal-form">
          {/* Booking Search */}
          <div className="form-group">
            <label>Search Booking (by reference)</label>
            {selectedSmsBooking ? (
              <div className="selected-booking-chip">
                <span>
                  <strong>{selectedSmsBooking.reference}</strong> - {selectedSmsBooking.customer_first_name} {selectedSmsBooking.customer_last_name}
                </span>
                <button type="button" onClick={clearSelectedBooking} className="chip-remove">×</button>
              </div>
            ) : (
              <div className="booking-search-container">
                <input
                  type="text"
                  value={smsBookingSearch}
                  onChange={(e) => {
                    setSmsBookingSearch(e.target.value)
                    searchBookingsForSms(e.target.value)
                  }}
                  placeholder="TAG-XXXXXX..."
                />
                {searchingSmsBookings && <span className="search-spinner">...</span>}
                {smsBookingResults.length > 0 && (
                  <div className="booking-search-results">
                    {smsBookingResults.map(booking => (
                      <div
                        key={booking.id}
                        className="booking-search-result"
                        onClick={() => selectBookingForSms(booking)}
                      >
                        <strong>{booking.reference}</strong>
                        <span>{booking.customer?.first_name} {booking.customer?.last_name}</span>
                        <small>{booking.customer?.phone}</small>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="form-group">
            <label>Phone Number *</label>
            <input
              type="tel"
              value={sendSmsForm.phone}
              onChange={(e) => setSendSmsForm(prev => ({ ...prev, phone: e.target.value }))}
              placeholder="07XXX XXXXXX"
            />
          </div>
          <div className="form-group">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <label style={{ margin: 0 }}>Message *</label>
              <select
                onChange={(e) => {
                  if (e.target.value) {
                    insertSmsVariable(e.target.value, sendSmsTextareaRef, sendSmsForm.content, setSendSmsForm)
                    e.target.value = ''
                  }
                }}
                style={{ padding: '6px 14px', fontSize: '0.75rem', borderRadius: '20px', background: '#f7b32b', color: '#1a1a2e', border: 'none', cursor: 'pointer', fontWeight: '600', width: 'auto', flexShrink: 0, textAlign: 'center', textAlignLast: 'center' }}
              >
                <option value="">Add Variable</option>
                {smsVariables.map(v => (
                  <option key={v.value} value={v.value}>{v.label}</option>
                ))}
              </select>
            </div>
            <textarea
              ref={sendSmsTextareaRef}
              value={sendSmsForm.content}
              onChange={(e) => setSendSmsForm(prev => ({ ...prev, content: e.target.value }))}
              placeholder="Enter your message..."
              rows={4}
              maxLength={480}
            />
            <small>{sendSmsForm.content.length}/480 characters ({Math.ceil(sendSmsForm.content.length / 160) || 0} SMS)</small>
          </div>
        </div>
        <div className="modal-actions">
          <button
            className="modal-btn modal-btn-secondary"
            onClick={() => {
              setShowSendSmsModal(false)
              setSendSmsForm({ phone: '', content: '', booking_id: '', customer_id: '' })
              setSelectedSmsBooking(null)
              setSmsBookingSearch('')
              setSmsBookingResults([])
              setEditingDraft(null)
            }}
          >
            Cancel
          </button>
          <button
            className="modal-btn"
            onClick={handleSaveDraft}
            disabled={savingDraft || !sendSmsForm.content}
            style={{ backgroundColor: '#e0e0e0', color: '#333', borderRadius: '20px' }}
          >
            {savingDraft ? 'Saving...' : (editingDraft ? 'Update Draft' : 'Save Draft')}
          </button>
          <button
            className="modal-btn modal-btn-primary"
            onClick={handleSendSms}
            disabled={sendingSms || !sendSmsForm.phone || !sendSmsForm.content}
          >
            {sendingSms ? 'Sending...' : 'Send SMS'}
          </button>
        </div>
      </div>
    </div>
  )}

  {/* Edit Template Modal */}
  {showEditTemplateModal && editingTemplate && (
    <div className="modal-overlay">
      <div className="modal-content modal-medium">
        <h3>Edit Template: {editingTemplate.name}</h3>
        <div className="modal-form">
          <div className="form-group">
            <label>Name</label>
            <input
              type="text"
              value={editingTemplate.name}
              onChange={(e) => setEditingTemplate(prev => ({ ...prev, name: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label>Description</label>
            <input
              type="text"
              value={editingTemplate.description || ''}
              onChange={(e) => setEditingTemplate(prev => ({ ...prev, description: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <label style={{ margin: 0 }}>Content</label>
              <select
                onChange={(e) => {
                  if (e.target.value) {
                    insertSmsVariable(e.target.value, editTemplateTextareaRef, editingTemplate.content, setEditingTemplate)
                    e.target.value = ''
                  }
                }}
                style={{ padding: '6px 14px', fontSize: '0.75rem', borderRadius: '20px', background: '#f7b32b', color: '#1a1a2e', border: 'none', cursor: 'pointer', fontWeight: '600', width: 'auto', flexShrink: 0, textAlign: 'center', textAlignLast: 'center' }}
              >
                <option value="">Add Variable</option>
                {smsVariables.map(v => (
                  <option key={v.value} value={v.value}>{v.label}</option>
                ))}
              </select>
            </div>
            <textarea
              ref={editTemplateTextareaRef}
              value={editingTemplate.content}
              onChange={(e) => setEditingTemplate(prev => ({ ...prev, content: e.target.value }))}
              rows={4}
              maxLength={480}
            />
            <small>{editingTemplate.content.length}/480 characters</small>
          </div>
          <div className="form-group">
            <label>Trigger Event</label>
            <select
              value={editingTemplate.trigger_event || ''}
              onChange={(e) => setEditingTemplate(prev => ({ ...prev, trigger_event: e.target.value || null, is_automated: !!e.target.value }))}
            >
              <option value="">None (Manual Only)</option>
              <option value="booking_confirmed">Booking Confirmed</option>
              <option value="parking_update">Parking Update</option>
              <option value="reminder_2day">2-Day Reminder</option>
              <option value="thank_you">Thank You (After Completion)</option>
            </select>
          </div>
          <div className="form-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={editingTemplate.is_active}
                onChange={(e) => setEditingTemplate(prev => ({ ...prev, is_active: e.target.checked }))}
              />
              Active
            </label>
          </div>
        </div>
        <div className="modal-actions">
          <button
            className="modal-btn modal-btn-secondary"
            onClick={() => {
              setShowEditTemplateModal(false)
              setEditingTemplate(null)
            }}
          >
            Cancel
          </button>
          <button
            className="modal-btn modal-btn-primary"
            onClick={handleSaveTemplate}
            disabled={savingTemplate}
          >
            {savingTemplate ? 'Saving...' : 'Save Template'}
          </button>
        </div>
      </div>
    </div>
  )}

  {/* Create Template Modal */}
  {showCreateTemplateModal && (
    <div className="modal-overlay">
      <div className="modal-content modal-medium">
        <h3>Create SMS Template</h3>
        <div className="modal-form">
          <div className="form-group">
            <label>Name *</label>
            <input
              type="text"
              value={newTemplate.name}
              onChange={(e) => setNewTemplate(prev => ({ ...prev, name: e.target.value }))}
              placeholder="e.g., Booking Reminder"
            />
          </div>
          <div className="form-group">
            <label>Description</label>
            <input
              type="text"
              value={newTemplate.description}
              onChange={(e) => setNewTemplate(prev => ({ ...prev, description: e.target.value }))}
              placeholder="Brief description of the template"
            />
          </div>
          <div className="form-group">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <label style={{ margin: 0 }}>Content *</label>
              <select
                onChange={(e) => {
                  if (e.target.value) {
                    insertSmsVariable(e.target.value, newTemplateTextareaRef, newTemplate.content, setNewTemplate)
                    e.target.value = ''
                  }
                }}
                style={{ padding: '6px 14px', fontSize: '0.75rem', borderRadius: '20px', background: '#f7b32b', color: '#1a1a2e', border: 'none', cursor: 'pointer', fontWeight: '600', width: 'auto', flexShrink: 0, textAlign: 'center', textAlignLast: 'center' }}
              >
                <option value="">Add Variable</option>
                {smsVariables.map(v => (
                  <option key={v.value} value={v.value}>{v.label}</option>
                ))}
              </select>
            </div>
            <textarea
              ref={newTemplateTextareaRef}
              value={newTemplate.content}
              onChange={(e) => setNewTemplate(prev => ({ ...prev, content: e.target.value }))}
              placeholder="Hi {{first_name}}, your booking {{booking_reference}} is confirmed..."
              rows={4}
              maxLength={480}
            />
            <small>{newTemplate.content.length}/480 characters. Use {'{{variable}}'} for dynamic content.</small>
          </div>
          <div className="form-group">
            <label>Trigger Event</label>
            <select
              value={newTemplate.trigger_event || ''}
              onChange={(e) => setNewTemplate(prev => ({ ...prev, trigger_event: e.target.value || null, is_automated: !!e.target.value }))}
            >
              <option value="">None (Manual Only)</option>
              <option value="booking_confirmed">Booking Confirmed</option>
              <option value="parking_update">Parking Update</option>
              <option value="reminder_2day">2-Day Reminder</option>
              <option value="thank_you">Thank You (After Completion)</option>
            </select>
          </div>
          <div className="form-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={newTemplate.is_active}
                onChange={(e) => setNewTemplate(prev => ({ ...prev, is_active: e.target.checked }))}
              />
              Active
            </label>
          </div>
        </div>
        <div className="modal-actions">
          <button
            className="modal-btn modal-btn-secondary"
            onClick={() => {
              setShowCreateTemplateModal(false)
              setNewTemplate({ name: '', content: '', description: '', is_active: true, trigger_event: null })
            }}
          >
            Cancel
          </button>
          <button
            className="modal-btn modal-btn-primary"
            onClick={handleCreateTemplate}
            disabled={creatingTemplate || !newTemplate.name || !newTemplate.content}
          >
            {creatingTemplate ? 'Creating...' : 'Create Template'}
          </button>
        </div>
      </div>
    </div>
  )}

  {/* Delete Template Confirmation Modal */}
  {templateToDelete && (
    <div className="modal-overlay" onClick={() => setTemplateToDelete(null)}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <h3>Delete Template</h3>
        <p>Are you sure you want to delete this template?</p>
        <div className="modal-booking-info">
          <p><strong>Name:</strong> {templateToDelete.name}</p>
          {templateToDelete.trigger_event && (
            <p><strong>Trigger:</strong> {templateToDelete.trigger_event}</p>
          )}
        </div>
        <div className="modal-actions">
          <button
            className="modal-btn modal-btn-secondary"
            onClick={() => setTemplateToDelete(null)}
          >
            Cancel
          </button>
          <button
            className="modal-btn modal-btn-danger"
            onClick={handleDeleteTemplate}
            disabled={deletingTemplateId === templateToDelete.id}
          >
            {deletingTemplateId === templateToDelete.id ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  )}

  {/* Delete Message Confirmation Modal */}
  {messageToDelete && (
    <div className="modal-overlay" onClick={() => setMessageToDelete(null)}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <h3>Delete Message</h3>
        <p>Are you sure you want to delete this message?</p>
        <div className="modal-booking-info">
          <p><strong>Phone:</strong> {formatPhoneForDisplay(messageToDelete.phone_number)}</p>
          <p><strong>Direction:</strong> {messageToDelete.direction === 'inbound' ? 'Inbound' : 'Outbound'}</p>
          <p><strong>Content:</strong> {messageToDelete.content?.substring(0, 100)}{messageToDelete.content?.length > 100 ? '...' : ''}</p>
          {messageToDelete.booking_reference && (
            <p><strong>Booking:</strong> {messageToDelete.booking_reference}</p>
          )}
        </div>
        <div className="modal-actions">
          <button
            className="modal-btn modal-btn-secondary"
            onClick={() => setMessageToDelete(null)}
          >
            Cancel
          </button>
          <button
            className="modal-btn modal-btn-danger"
            onClick={handleDeleteMessage}
            disabled={deletingMessageId === messageToDelete.id}
          >
            {deletingMessageId === messageToDelete.id ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  )}
</div>
  )
}

export default MessagesSection
