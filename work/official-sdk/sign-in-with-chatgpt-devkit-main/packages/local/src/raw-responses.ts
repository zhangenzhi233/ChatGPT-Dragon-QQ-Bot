// Added for ChatGPT-Dragon-QQ-Bot (2026-10-09): raw Responses stream forwarding.
// Licensed under Sign-in with ChatGPT DevKit Noncommercial License v1.0.
// Local addition (2026-10-03): raw Responses streaming for a personal QQ experiment.
// Licensed under the repository's Sign-in with ChatGPT DevKit Noncommercial License.
import { apiError, ChatGPTError, fetchRemote, isObject, jsonResponse } from "./errors.js";
import type { StreamRawResponseOptions } from "./types.js";

const MAX_EVENT = 16 * 1024 * 1024;

async function consumeEvent(callback: () => void | Promise<void>, signal: AbortSignal): Promise<void> {
  let abort: () => void = () => undefined;
  const cancelled = new Promise<never>((_resolve, reject) => {
    abort = () => reject(new ChatGPTError("cancelled", "The response was cancelled."));
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
  });
  try { await Promise.race([Promise.resolve().then(callback), cancelled]); }
  finally { signal.removeEventListener("abort", abort); }
}

/** Internal transport. OAuth credentials must never cross the public client interface. */
export async function streamRawResponse(
  accessToken: string,
  options: StreamRawResponseOptions,
  signal: AbortSignal,
): Promise<Record<string, unknown>> {
  // Snapshot JSON before forcing invariants, so mutation/toJSON cannot override them.
  let body: unknown;
  try { body = JSON.parse(JSON.stringify(options.body)) as unknown; }
  catch { throw new ChatGPTError("invalid_request", "Use a JSON object for the Responses request."); }
  if (!isObject(body) || typeof body.model !== "string" || !body.model.trim() || !Array.isArray(body.input)) {
    throw new ChatGPTError("invalid_request", "Provide a model and an input array for the Responses request.");
  }
  signal.throwIfAborted();
  const response = await fetchRemote("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: { authorization: `Bearer ${accessToken}`, "content-type": "application/json", accept: "text/event-stream" },
    body: JSON.stringify({ ...body, store: false, stream: true }),
    signal,
  }, 180_000);
  const receivedRequestId = response.headers.get("x-request-id");
  const requestId = accessToken && receivedRequestId?.includes(accessToken) ? null : receivedRequestId;
  if (!response.ok) {
    try { throw apiError(await jsonResponse(response), response.status, requestId); }
    catch (error) {
      // Diagnostics may contain untrusted identifiers; never return a reflected bearer.
      if (accessToken && error instanceof ChatGPTError && JSON.stringify(error.toJSON()).includes(accessToken)) {
        throw new ChatGPTError("api_error", "ChatGPT could not complete this request.", response.status >= 500, response.status);
      }
      throw error;
    }
  }
  const contentType = response.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
  if (!response.body || (contentType && contentType !== "text/event-stream")) {
    await response.body?.cancel();
    throw new ChatGPTError("invalid_stream", "ChatGPT did not return the expected response stream.", true, response.status);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  let dataLines: string[] = [];
  let eventSize = 0;
  let completed: Record<string, unknown> | undefined;
  const streamedOutput = new Map<number, Record<string, unknown>>();
  const onAbort = () => { void reader.cancel().catch(() => undefined); };
  signal.addEventListener("abort", onAbort, { once: true });

  const dispatch = async () => {
    const data = dataLines.join("\n");
    dataLines = [];
    eventSize = 0;
    if (!data || data === "[DONE]") return;
    let event: unknown;
    try { event = JSON.parse(data) as unknown; }
    catch { throw new ChatGPTError("invalid_stream", "ChatGPT returned an invalid stream event.", true); }
    if (!isObject(event) || typeof event.type !== "string") {
      throw new ChatGPTError("invalid_stream", "ChatGPT returned an invalid stream event.", true);
    }
    // Reject credential reflection instead of forwarding it into a local client.
    if (accessToken && JSON.stringify(event).includes(accessToken)) {
      throw new ChatGPTError("invalid_stream", "ChatGPT returned an unsafe stream event.");
    }
    if (event.type === "response.failed" || event.type === "error") {
      throw apiError(isObject(event.response) ? event.response : event, response.status, requestId);
    }
    if (event.type === "response.incomplete") {
      throw new ChatGPTError("response_incomplete", "ChatGPT stopped before completing the response.", true);
    }
    if (event.type === "response.output_item.done" && isObject(event.item)) {
      const index = Number.isInteger(event.output_index) && Number(event.output_index) >= 0
        ? Number(event.output_index) : streamedOutput.size;
      streamedOutput.set(index, structuredClone(event.item));
    }
    if (event.type === "response.completed") {
      if (!isObject(event.response) || event.response.status !== "completed" || !Array.isArray(event.response.output)) {
        throw new ChatGPTError("invalid_stream", "ChatGPT returned an invalid completed response.", true);
      }
      // ChatGPT plan streams can complete with an empty summary output even when
      // fully finished items were emitted earlier. Rebuild only from done items.
      if (event.response.output.length === 0 && streamedOutput.size > 0) {
        event.response.output = [...streamedOutput.entries()].sort(([left], [right]) => left - right).map(([, item]) => item);
      }
      completed = structuredClone(event.response);
    }
    signal.throwIfAborted();
    if (options.onEvent) await consumeEvent(() => options.onEvent!(event), signal);
    signal.throwIfAborted();
  };
  const line = async (value: string) => {
    if (value === "") { await dispatch(); return; }
    if (value.startsWith("data:")) {
      const content = value.slice(5).replace(/^ /, "");
      eventSize += content.length;
      if (eventSize > MAX_EVENT) throw new ChatGPTError("invalid_stream", "ChatGPT returned an oversized stream event.");
      dataLines.push(content);
    }
  };
  try {
    for (;;) {
      signal.throwIfAborted();
      const chunk = await reader.read();
      signal.throwIfAborted();
      pending += decoder.decode(chunk.value, { stream: !chunk.done });
      let consumed = 0;
      for (let index = 0; index < pending.length; index++) {
        const character = pending[index];
        if (character !== "\n" && character !== "\r") continue;
        if (character === "\r" && index === pending.length - 1 && !chunk.done) break;
        await line(pending.slice(consumed, index));
        if (character === "\r" && pending[index + 1] === "\n") index++;
        consumed = index + 1;
        if (completed) break;
      }
      if (completed) return completed;
      pending = pending.slice(consumed);
      if (pending.length > MAX_EVENT) throw new ChatGPTError("invalid_stream", "ChatGPT returned an oversized stream event.");
      if (chunk.done) {
        if (pending) await line(pending);
        await dispatch();
        if (completed) return completed;
        throw new ChatGPTError("stream_interrupted", "The response ended before completion.", true);
      }
    }
  } catch (error) {
    if (signal.aborted) throw new ChatGPTError("cancelled", "The response was cancelled.");
    if (error instanceof ChatGPTError) throw error;
    throw new ChatGPTError("stream_interrupted", "The response stream or its consumer was interrupted.", true);
  } finally {
    signal.removeEventListener("abort", onAbort);
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
