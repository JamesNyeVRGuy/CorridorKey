"""GPU worker subprocess entry point.

Each GPU worker runs as a separate OS process with CUDA_VISIBLE_DEVICES
set so that CorridorKeyService always sees one GPU as cuda:0.

Protocol (via multiprocessing.Queue):
    Input:  {"action": "run", "job": <serialized GPUJob dict>, "clips_dir": str}
    Output: {"status": "started"|"progress"|"completed"|"failed", ...}
    Input:  {"action": "stop"} — graceful shutdown
"""

from __future__ import annotations

import logging
import os
import traceback
from multiprocessing import Queue
from typing import Any

logger = logging.getLogger(__name__)


def _serialize_job(job) -> dict[str, Any]:
    """Serialize a GPUJob to a dict for cross-process transfer."""
    return {
        "id": job.id,
        "job_type": job.job_type.value,
        "clip_name": job.clip_name,
        "params": job.params,
    }


def gpu_worker_main(gpu_index: int, task_queue: Queue, result_queue: Queue) -> None:
    """Main function for a GPU worker subprocess.

    Args:
        gpu_index: Physical GPU index (sets CUDA_VISIBLE_DEVICES).
        task_queue: Receives job dicts to process.
        result_queue: Sends status updates back to the parent.
    """
    # Set GPU visibility BEFORE importing torch
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_index)

    from backend.job_queue import GPUJob, JobType
    from backend.service import CorridorKeyService, InferenceParams, OutputConfig

    service = CorridorKeyService()
    device = service.detect_device()
    result_queue.put({"status": "ready", "gpu_index": gpu_index, "device": device})
    logger.info(f"GPU worker subprocess started: GPU {gpu_index}, device={device}")

    while True:
        try:
            msg = task_queue.get()
        except Exception:
            break

        if msg.get("action") == "stop":
            logger.info(f"GPU worker {gpu_index} shutting down")
            break

        if msg.get("action") != "run":
            continue

        job_dict = msg["job"]
        clips_dir = msg["clips_dir"]
        job_id = job_dict["id"]

        try:
            result_queue.put({"status": "started", "job_id": job_id, "gpu_index": gpu_index})

            job_type = JobType(job_dict["job_type"])
            clip_name = job_dict["clip_name"]
            params = job_dict.get("params", {})

            # Find the clip
            clips = service.scan_clips(clips_dir)
            clip = next((c for c in clips if c.name == clip_name), None)
            if clip is None:
                result_queue.put({"status": "failed", "job_id": job_id, "error": f"Clip '{clip_name}' not found"})
                continue

            # Build a real GPUJob for cancel checking
            job = GPUJob(job_type=job_type, clip_name=clip_name, params=params)
            job.id = job_id  # preserve original ID

            _jid = job_id  # bind for closures (B023)

            def on_progress(cn: str, current: int, total: int, _id: str = _jid) -> None:
                result_queue.put(
                    {"status": "progress", "job_id": _id, "clip_name": cn, "current": current, "total": total}
                )

            def on_warning(message: str, _id: str = _jid) -> None:
                result_queue.put({"status": "warning", "job_id": _id, "message": message})

            if job_type == JobType.INFERENCE:
                inf_params = InferenceParams.from_dict(params.get("inference_params", {}))
                output_config = OutputConfig.from_dict(params.get("output_config", {}))
                frame_range = params.get("frame_range")
                service.run_inference(
                    clip,
                    inf_params,
                    job=job,
                    on_progress=on_progress,
                    on_warning=on_warning,
                    output_config=output_config,
                    frame_range=tuple(frame_range) if frame_range else None,
                )
            elif job_type == JobType.GVM_ALPHA:
                service.run_gvm(clip, job=job, on_progress=on_progress, on_warning=on_warning)
            elif job_type == JobType.VIDEOMAMA_ALPHA:
                chunk_size = params.get("chunk_size", 50)
                service.run_videomama(
                    clip, job=job, on_progress=on_progress, on_warning=on_warning, chunk_size=chunk_size
                )
            else:
                err = f"Unsupported job type: {job_type.value}"
                result_queue.put({"status": "failed", "job_id": job_id, "error": err})
                continue

            result_queue.put(
                {
                    "status": "completed",
                    "job_id": job_id,
                    "clip_name": clip_name,
                    "clip_state": clip.state.value,
                }
            )

        except Exception as e:
            result_queue.put(
                {
                    "status": "failed",
                    "job_id": job_id,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )

    service.unload_engines()
    logger.info(f"GPU worker {gpu_index} exited cleanly")
