<script lang="ts">
</script>

<svelte:head>
	<title>Pending Approval — CorridorKey</title>
</svelte:head>

<div class="auth-page">
	<div class="auth-card">
		<img src="/Corridor_Digital_Logo.svg" alt="Corridor Digital" class="auth-logo" />
		<h1 class="auth-title mono">CORRIDORKEY</h1>

		<div class="pending-icon">
			<svg width="48" height="48" viewBox="0 0 48 48" fill="none">
				<circle cx="24" cy="24" r="20" stroke="var(--state-queued)" stroke-width="2" />
				<path d="M24 14v12l8 4" stroke="var(--state-queued)" stroke-width="2" stroke-linecap="round" />
			</svg>
		</div>

		<h2 class="pending-title">Account Pending Approval</h2>
		<p class="pending-text">
			Your account has been created. An admin will review and approve your access.
			You'll be able to sign in once approved.
		</p>

		<div class="auth-footer">
			<a href="/login">Back to sign in</a>
		</div>
	</div>
</div>

<style>
	.auth-page {
		display: flex;
		align-items: center;
		justify-content: center;
		min-height: 100vh;
		background: var(--surface-0);
		padding: var(--sp-4);
	}

	.auth-card {
		width: 100%;
		max-width: 380px;
		background: var(--surface-1);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: var(--sp-6);
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--sp-4);
		text-align: center;
	}

	.auth-logo { width: 120px; filter: drop-shadow(0 0 4px rgba(255, 242, 3, 0.15)); }
	.auth-title { font-size: 11px; letter-spacing: 0.2em; color: var(--text-tertiary); }

	.pending-icon { margin: var(--sp-2) 0; }

	.pending-title {
		font-size: 18px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.pending-text {
		font-size: 14px;
		color: var(--text-secondary);
		line-height: 1.5;
	}

	.auth-footer { font-size: 13px; }
	.auth-footer a { color: var(--accent); }
</style>
