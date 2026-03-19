ORACLE_RED = "#c74634"
ORACLE_GOLD = "#bc9557"

CUSTOM_CSS = """
:root {
  --oracle-red: #c74634;
  --oracle-gold: #bc9557;
  --surface-base: #f2ece5;
  --surface-chat: #fffdf9;
  --border-subtle: #dccfc2;
  --text-primary: #1b2432;
  --text-muted: #5c6576;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --radius-sm: 10px;
  --radius-md: 16px;
  --shadow-sm: 0 2px 6px rgba(15, 23, 42, 0.07);
  --shadow-md: 0 14px 30px rgba(15, 23, 42, 0.09);
}

.gradio-container {
  background: linear-gradient(180deg, #f8f4ee 0%, var(--surface-base) 100%);
  color: var(--text-primary);
}

.top-masthead,
.chat-surface,
.composer-dock,
.quick-prompts-panel {
  border-radius: var(--radius-md);
}

.top-masthead {
  border: 1px solid var(--border-subtle);
  background: linear-gradient(135deg, rgba(199, 70, 52, 0.12) 0%, rgba(255, 255, 255, 0.98) 34%, rgba(188, 149, 87, 0.12) 100%);
  box-shadow: var(--shadow-sm);
  padding: var(--space-4) var(--space-5);
  margin-bottom: var(--space-4);
}


.masthead-row,
.action-row,
.choice-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.top-masthead .gr-group {
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
  padding: 0 !important;
}

.masthead-row {
  display: grid !important;
  grid-template-columns: 1fr;
  align-items: flex-start;
  gap: 28px;
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 18px;
  flex: 1 1 520px;
  min-width: 320px;
}

.brand-block img {
  height: 54px;
  width: auto;
  flex: 0 0 auto;
}

.brand-block > div {
  min-width: 0;
}

.brand-title {
  margin: 0;
  font-size: 1.08rem;
  font-weight: 700;
  line-height: 1.2;
}

.brand-subtitle {
  margin: 4px 0 0;
  font-size: 0.84rem;
  line-height: 1.45;
  color: var(--text-muted);
  max-width: 520px;
}

.masthead-chip-controls {
  min-width: 0;
  width: 100%;
  background: #fff;
  border: 1px solid rgba(199, 70, 52, 0.14);
  border-radius: 18px;
  box-shadow: 0 10px 24px rgba(80, 54, 35, 0.08);
  padding: 14px 16px;
}

.chip-row {
  display: grid !important;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  justify-content: stretch;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.info-chip,
.bucket-chip-wrap {
  display: inline-flex;
  align-items: center;
  min-height: 42px;
  border: 1px solid #d8ccbf;
  border-radius: 14px;
  background: #fff;
  box-shadow: none;
}

.info-chip {
  padding: 0 14px;
  font-size: 0.78rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.info-chip strong,
.bucket-chip-label {
  margin-right: 8px;
  font-weight: 700;
  color: #7a2d20;
  white-space: nowrap;
}

.bucket-chip-wrap {
  gap: 10px;
  padding: 0 8px 0 14px;
  min-width: 0;
  max-width: none;
  width: 100%;
}

.chip-row > .gr-html > div,
.chip-row > .gr-row {
  height: 100%;
}

.bucket-chip-dropdown {
  min-width: 0;
  width: 100%;
}

.bucket-chip-dropdown > div,
.bucket-chip-dropdown .gradio-dropdown,
.top-masthead .gradio-dropdown,
.top-masthead .gradio-dropdown .wrap,
.top-masthead .gradio-dropdown .inner-wrap,
.top-masthead .gradio-dropdown .dropdown-container {
  min-width: 0;
  width: 100%;
}

.bucket-chip-dropdown button,
.bucket-chip-dropdown input {
  font-size: 0.78rem !important;
  min-height: 34px !important;
}

.bucket-chip-dropdown button {
  border-radius: 12px !important;
  border: 1px solid rgba(199, 70, 52, 0.18) !important;
  background: #fff7f4 !important;
  box-shadow: none !important;
}

.bucket-chip-dropdown button:hover {
  background: #fff0ea !important;
  border-color: rgba(199, 70, 52, 0.3) !important;
}

.bucket-chip-dropdown svg {
  color: #7a2d20 !important;
}

.top-masthead .gradio-dropdown,
.top-masthead .gr-button,
.top-masthead .gr-markdown,
.top-masthead .gr-html,
.chat-surface .gradio-dropdown,
.chat-surface .gr-button,
.chat-surface .gr-markdown {
  min-width: 0;
}

.runtime-storage-note {
  color: var(--text-muted);
}

.chip-row > .gr-html,
.chip-row > .gr-row,
.chip-row > .gradio-row {
  min-width: 0;
  width: 100%;
}

.chip-row > .gr-html:last-child {
  justify-self: stretch;
}

.frame-wrap {
  max-width: 1440px;
  margin: 0 auto;
  width: 100%;
}

.chat-workspace {
  min-height: calc(100vh - 260px);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.chat-surface {
  background: var(--surface-chat);
  border: 1px solid #dccfc1;
  box-shadow: var(--shadow-md);
  padding: var(--space-4);
}

.choice-detail {
  border: 1px solid #ddd1c4;
  border-radius: var(--radius-sm);
  background: #fff;
  padding: var(--space-2);
}

.quick-prompts-panel {
  background: transparent;
  border: 0;
  box-shadow: none;
  padding: 0;
}

.quick-prompts-title {
  color: #7a2d20 !important;
  font-weight: 700;
  margin-bottom: 8px !important;
}

.quick-prompts-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.quick-prompt-chip,
.quick-prompt-chip button {
  min-height: 42px;
  border-radius: 14px !important;
  border: 1px solid #d8ccbf !important;
  background: #fff !important;
  color: #7a2d20 !important;
  font-weight: 600 !important;
  box-shadow: none !important;
  padding: 0 14px !important;
}

.quick-prompt-chip:hover,
.quick-prompt-chip button:hover {
  background: #fff7f4 !important;
  border-color: rgba(199, 70, 52, 0.36) !important;
}

.composer-dock {
  position: sticky;
  bottom: var(--space-2);
  background: var(--surface-chat);
  border: 1px solid #d7cabd;
  padding: var(--space-3);
}

.working-inline { display: inline-flex; align-items: center; gap: 8px; }
.working-spinner {
  width: 12px; height: 12px; border-radius: 50%;
  border: 2px solid rgba(106, 45, 36, 0.24);
  border-top-color: rgba(106, 45, 36, 0.95);
  animation: runSpin 0.9s linear infinite;
}

.working-dots span {
  width: 4px; height: 4px; border-radius: 50%;
  background: #8f5a2e; opacity: 0.35; animation: dotPulse 1s infinite ease-in-out;
}

.footer {
  text-align: center;
  color: #666f7d;
  font-size: 0.78rem;
  margin-top: var(--space-3);
}

@keyframes runSpin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
@keyframes dotPulse { 0%,100% { opacity: 0.28; } 50% { opacity: 1; } }

@media (max-width: 1200px) {
  .chip-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .bucket-chip-wrap {
    grid-column: 1 / -1;
  }

  .chip-row > .gr-html:last-child {
    justify-self: start;
  }
}

@media (max-width: 768px) {
  .top-masthead {
    padding: 14px;
  }

  .masthead-chip-controls {
    padding: 12px;
  }

  .brand-block {
    align-items: flex-start;
    gap: 14px;
    min-width: 0;
  }

  .brand-block img {
    height: 42px;
  }

  .brand-subtitle {
    max-width: none;
  }

  .chip-row {
    grid-template-columns: 1fr;
    align-items: stretch;
  }

  .info-chip,
  .bucket-chip-wrap {
    width: 100%;
    max-width: none;
  }

  .bucket-chip-wrap {
    border-radius: 14px;
    padding: 10px 12px;
    min-width: 0;
    flex-wrap: wrap;
  }

  .bucket-chip-dropdown {
    width: 100%;
  }

  .quick-prompts-row {
    flex-direction: column;
    align-items: stretch;
  }

  .quick-prompt-chip,
  .quick-prompt-chip button {
    width: 100%;
  }

  .chip-row > .gr-html:last-child {
    justify-self: stretch;
  }
}
"""