import * as z from "zod/v4";

const READ_ONLY_ANNOTATIONS = {
  readOnlyHint: true,
  destructiveHint: false,
  idempotentHint: true,
  openWorldHint: false,
};

const DESTRUCTIVE_ANNOTATIONS = {
  readOnlyHint: false,
  destructiveHint: true,
  idempotentHint: true,
  openWorldHint: false,
};

function result(data) {
  return {
    content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
    structuredContent: data,
  };
}

function failure(message) {
  return {
    content: [{ type: "text", text: message }],
    isError: true,
  };
}

export function registerComposeTools(server) {
  const baseUrl = process.env.MCP_COMPOSE_AGENT_URL?.replace(/\/+$/, "");
  const token = process.env.MCP_COMPOSE_AGENT_TOKEN;
  if (!baseUrl || !token) return;

  async function request(path, options = {}) {
    const response = await fetch(`${baseUrl}${path}`, {
      ...options,
      headers: {
        authorization: `Bearer ${token}`,
        "content-type": "application/json",
        ...(options.headers ?? {}),
      },
      signal: AbortSignal.timeout(10 * 60 * 1000),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(
        typeof payload.error === "string"
          ? payload.error
          : `Compose agent returned HTTP ${response.status}`,
      );
    }
    return payload;
  }

  server.registerTool(
    "unraid_list_compose_stacks",
    {
      title: "List allowlisted Unraid Compose stacks",
      description:
        "List the Docker Compose stacks explicitly allowlisted for remote management and their current managed image.",
      inputSchema: z.object({}).strict(),
      annotations: READ_ONLY_ANNOTATIONS,
    },
    async () => {
      try {
        return result(await request("/v1/stacks"));
      } catch (error) {
        return failure(error instanceof Error ? error.message : "Compose agent request failed");
      }
    },
  );

  server.registerTool(
    "unraid_update_compose_stack",
    {
      title: "Update an allowlisted Unraid Compose stack",
      description:
        "Set the managed service to an immutable sha-* image, pull the stack, recreate it, wait for health, and restore the previous image if recreation fails.",
      inputSchema: z
        .object({
          stack: z.string().regex(/^[a-z0-9][a-z0-9_-]{0,63}$/),
          image: z
            .string()
            .min(1)
            .max(512)
            .describe("Full image reference ending in an immutable sha-* tag"),
          confirmation: z.literal("UPDATE_COMPOSE_STACK"),
        })
        .strict(),
      annotations: DESTRUCTIVE_ANNOTATIONS,
    },
    async ({ stack, image, confirmation }) => {
      try {
        return result(
          await request("/v1/stacks/update", {
            method: "POST",
            body: JSON.stringify({ stack, image, confirmation }),
          }),
        );
      } catch (error) {
        return failure(error instanceof Error ? error.message : "Compose update failed");
      }
    },
  );
}
