<script lang="ts">
	import { onMount } from 'svelte';
	import { nodes, refreshNodes, type NodeInfo } from '$lib/stores/nodes';
	import { api } from '$lib/api';
	import { toast } from '$lib/stores/toasts';

	interface LocalGPU {
		index: number;
		name: string;
		vram_total_gb: number;
		vram_free_gb: number;
	}

	let localGpus = $state<LocalGPU[]>([]);

	onMount(() => {
		refreshNodes();
		api.system2.localGpus().then((gpus) => (localGpus = gpus)).catch(() => {});
		const interval = setInterval(refreshNodes, 5000);
		return () => clearInterval(interval);
	});

	function timeSince(ts: number): string {
		const seconds = Math.floor((Date.now() / 1000) - ts);
		if (seconds < 10) return 'just now';
		if (seconds < 60) return `${seconds}s ago`;
		if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
		return `${Math.floor(seconds / 3600)}h ago`;
	}

	function statusClass(status: string): string {
		if (status === 'online') return 'status-online';
		if (status === 'busy') return 'status-busy';
		return 'status-offline';
	}

	async function removeNode(nodeId: string) {
		try {
			await api.nodes.remove(nodeId);
			refreshNodes();
		} catch (e: unknown) {
			toast.error(`Failed to remove node: ${e instanceof Error ? e.message : e}`);
		}
	}
</script>

<div class="page">
	<header class="page-header">
		<h1 class="mono">RENDER FARM</h1>
		<p class="subtitle">Remote worker nodes and GPU status</p>
	</header>

	<!-- Local GPUs -->
	<section class="section">
		<h2 class="section-title mono">LOCAL GPUS</h2>
		{#if localGpus.length === 0}
			<div class="empty-state mono">No GPUs detected</div>
		{:else}
			<div class="gpu-grid">
				{#each localGpus as gpu}
					<div class="gpu-card">
						<div class="gpu-header">
							<span class="gpu-index mono">GPU {gpu.index}</span>
							<span class="gpu-name">{gpu.name}</span>
						</div>
						<div class="gpu-vram">
							<div class="vram-bar">
								<div
									class="vram-used"
									style="width: {gpu.vram_total_gb > 0 ? ((gpu.vram_total_gb - gpu.vram_free_gb) / gpu.vram_total_gb) * 100 : 0}%"
								></div>
							</div>
							<span class="vram-label mono">{gpu.vram_free_gb.toFixed(1)} / {gpu.vram_total_gb.toFixed(1)} GB free</span>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</section>

	<!-- Remote Nodes -->
	<section class="section">
		<h2 class="section-title mono">
			REMOTE NODES
			{#if $nodes.length > 0}
				<span class="count-badge mono">{$nodes.length}</span>
			{/if}
		</h2>

		{#if $nodes.length === 0}
			<div class="empty-state">
				<p class="mono">No remote nodes connected</p>
				<div class="instructions">
					<p>Start a node agent on a remote machine:</p>
					<code class="mono">CK_MAIN_URL=http://this-machine:3000 uv run python -m web.node</code>
				</div>
			</div>
		{:else}
			<div class="node-list">
				{#each $nodes as node (node.node_id)}
					<div class="node-card" class:offline={node.status === 'offline'}>
						<div class="node-header">
							<span class="node-dot {statusClass(node.status)}"></span>
							<span class="node-name">{node.name}</span>
							<span class="node-host mono">{node.host}</span>
							<span class="node-status mono {statusClass(node.status)}">{node.status.toUpperCase()}</span>
							<button class="btn-remove" title="Remove node" onclick={() => removeNode(node.node_id)}>
								<svg width="14" height="14" viewBox="0 0 16 16" fill="none">
									<path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
								</svg>
							</button>
						</div>

						{#if node.gpus && node.gpus.length > 0}
							<div class="node-gpus">
								{#each node.gpus as gpu}
									<div class="gpu-row">
										<span class="gpu-slot-dot" class:busy={gpu.status === 'busy'}></span>
										<span class="gpu-slot-index mono">GPU {gpu.index}</span>
										<span class="gpu-slot-name">{gpu.name}</span>
										<div class="gpu-slot-vram">
											<div class="vram-bar small">
												<div
													class="vram-used"
													style="width: {gpu.vram_total_gb > 0 ? ((gpu.vram_total_gb - gpu.vram_free_gb) / gpu.vram_total_gb) * 100 : 0}%"
												></div>
											</div>
											<span class="vram-label mono">{gpu.vram_free_gb.toFixed(1)}G</span>
										</div>
										{#if gpu.current_job_id}
											<span class="gpu-job mono">{gpu.current_job_id}</span>
										{/if}
									</div>
								{/each}
							</div>
						{:else if node.gpu_name}
							<div class="node-gpu-legacy">
								<span class="gpu-name">{node.gpu_name}</span>
								<span class="vram-label mono">{node.vram_free_gb.toFixed(1)} / {node.vram_total_gb.toFixed(1)} GB</span>
							</div>
						{/if}

						<div class="node-footer">
							<span class="node-caps mono">{node.capabilities.join(', ')}</span>
							{#if node.shared_storage}
								<span class="node-shared mono" title={node.shared_storage}>SHARED</span>
							{/if}
							<span class="node-heartbeat mono">{timeSince(node.last_heartbeat)}</span>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</section>
</div>

<style>
	.page {
		padding: var(--sp-6);
		max-width: 900px;
	}

	.page-header {
		margin-bottom: var(--sp-6);
	}

	.page-header h1 {
		font-size: 20px;
		font-weight: 600;
		color: var(--text-primary);
		letter-spacing: 0.1em;
	}

	.subtitle {
		color: var(--text-tertiary);
		font-size: 13px;
		margin-top: var(--sp-1);
	}

	.section {
		margin-bottom: var(--sp-8);
	}

	.section-title {
		font-size: 11px;
		font-weight: 600;
		color: var(--text-tertiary);
		letter-spacing: 0.15em;
		margin-bottom: var(--sp-3);
		display: flex;
		align-items: center;
		gap: var(--sp-2);
	}

	.count-badge {
		font-size: 9px;
		background: var(--accent);
		color: #000;
		padding: 1px 6px;
		border-radius: 8px;
		font-weight: 700;
	}

	.empty-state {
		color: var(--text-tertiary);
		padding: var(--sp-6) var(--sp-4);
		text-align: center;
		border: 1px dashed var(--border);
		border-radius: var(--radius-md, 6px);
	}

	.instructions {
		margin-top: var(--sp-3);
		font-size: 13px;
	}

	.instructions code {
		display: block;
		margin-top: var(--sp-2);
		padding: var(--sp-2) var(--sp-3);
		background: var(--surface-2);
		border-radius: 4px;
		font-size: 12px;
		color: var(--accent);
		word-break: break-all;
	}

	/* GPU grid (local) */
	.gpu-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
		gap: var(--sp-3);
	}

	.gpu-card {
		background: var(--surface-1);
		border: 1px solid var(--border);
		border-radius: 6px;
		padding: var(--sp-3);
	}

	.gpu-header {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		margin-bottom: var(--sp-2);
	}

	.gpu-index {
		font-size: 10px;
		color: var(--accent);
		font-weight: 600;
	}

	.gpu-name {
		font-size: 13px;
		color: var(--text-secondary);
	}

	.gpu-vram {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
	}

	.vram-bar {
		flex: 1;
		height: 4px;
		background: var(--surface-3);
		border-radius: 2px;
		overflow: hidden;
	}

	.vram-bar.small {
		max-width: 60px;
	}

	.vram-used {
		height: 100%;
		background: var(--accent);
		border-radius: 2px;
		transition: width 0.3s;
	}

	.vram-label {
		font-size: 10px;
		color: var(--text-tertiary);
		white-space: nowrap;
	}

	/* Node list */
	.node-list {
		display: flex;
		flex-direction: column;
		gap: var(--sp-2);
	}

	.node-card {
		background: var(--surface-1);
		border: 1px solid var(--border);
		border-radius: 6px;
		padding: var(--sp-3) var(--sp-4);
		transition: border-color 0.2s;
	}

	.node-card:hover {
		border-color: var(--border-active);
	}

	.node-card.offline {
		opacity: 0.5;
	}

	.node-header {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
	}

	.node-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.status-online { background: var(--state-complete); box-shadow: 0 0 6px rgba(93, 216, 121, 0.4); }
	.status-busy { background: var(--accent); box-shadow: 0 0 6px rgba(255, 242, 3, 0.4); }
	.status-offline { background: var(--state-error); }

	.node-name {
		font-size: 14px;
		font-weight: 500;
		color: var(--text-primary);
	}

	.node-host {
		font-size: 11px;
		color: var(--text-tertiary);
	}

	.node-status {
		margin-left: auto;
		font-size: 9px;
		letter-spacing: 0.08em;
		padding: 1px 6px;
		border: 1px solid currentColor;
		border-radius: 3px;
	}

	.btn-remove {
		background: none;
		border: none;
		color: var(--text-tertiary);
		cursor: pointer;
		padding: 2px;
		border-radius: 3px;
		display: flex;
		align-items: center;
		margin-left: var(--sp-1);
	}

	.btn-remove:hover {
		color: var(--state-error);
		background: rgba(255, 82, 82, 0.1);
	}

	/* Multi-GPU rows */
	.node-gpus {
		margin-top: var(--sp-2);
		padding-left: 18px;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.gpu-row {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		font-size: 12px;
	}

	.gpu-slot-dot {
		width: 5px;
		height: 5px;
		border-radius: 50%;
		background: var(--state-complete);
		flex-shrink: 0;
	}

	.gpu-slot-dot.busy {
		background: var(--accent);
	}

	.gpu-slot-index {
		font-size: 10px;
		color: var(--text-tertiary);
	}

	.gpu-slot-name {
		color: var(--text-secondary);
		font-size: 12px;
	}

	.gpu-slot-vram {
		display: flex;
		align-items: center;
		gap: 4px;
		margin-left: auto;
	}

	.gpu-job {
		font-size: 10px;
		color: var(--accent);
		padding: 0 4px;
		background: var(--accent-muted);
		border-radius: 3px;
	}

	/* Legacy single GPU */
	.node-gpu-legacy {
		margin-top: var(--sp-2);
		padding-left: 18px;
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		font-size: 12px;
	}

	.node-footer {
		margin-top: var(--sp-2);
		display: flex;
		align-items: center;
		gap: var(--sp-3);
		padding-top: var(--sp-2);
		border-top: 1px solid var(--border-subtle);
	}

	.node-caps {
		font-size: 10px;
		color: var(--text-tertiary);
	}

	.node-shared {
		font-size: 9px;
		color: var(--state-complete);
		padding: 0 4px;
		border: 1px solid currentColor;
		border-radius: 3px;
	}

	.node-heartbeat {
		margin-left: auto;
		font-size: 10px;
		color: var(--text-tertiary);
	}
</style>
