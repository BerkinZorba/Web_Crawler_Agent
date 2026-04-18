# Multi-Agent Workflow

## 1. Overview

This project was developed using a multi-agent AI workflow, as required by the assignment. The final submitted system is not a runtime platform composed of autonomous agents. Instead, the multi-agent requirement was satisfied through the development process itself.

In this workflow, separate agents were assigned responsibility for different parts of the system. Each agent had a defined scope, expected inputs, required outputs, and completion criteria. This made the design process more structured, reduced responsibility overlap, and forced architectural decisions to be made explicitly rather than implicitly during coding.

The final software system is a Python-based localhost web crawler and search engine. The multi-agent aspect is in how the system was designed, reviewed, documented, and managed from scratch.

---

## 2. Why a Multi-Agent Workflow Was Used

A project like this can easily become messy if everything is handled in one stream of prompts or one unstructured implementation pass. The assignment also explicitly asks for agent definition, responsibility assignment, interaction decisions, and evaluation of outputs.

Because of that, the development process was split into role-based agents. The goal was not to pretend that multiple agents were needed at runtime, but to use specialized agents to improve clarity during design and implementation.

This workflow helped in four practical ways:

1. It separated architecture from implementation.
2. It separated storage concerns from crawl logic.
3. It separated search design from crawl mechanics.
4. It created a formal review step before features were treated as complete.

That made the final project easier to justify in terms of architectural sensibility and requirement coverage.

---

## 3. Agent Set

The workflow used six agents:

1. Architect Agent
2. Crawl Engineer Agent
3. Storage Engineer Agent
4. Index and Search Engineer Agent
5. QA Reviewer Agent
6. Documentation and Integration Agent

These agents were chosen because they map cleanly to the real concerns of the assignment without artificially inflating the workflow.

---

## 4. Agent Responsibilities

### 4.1 Architect Agent

The Architect Agent defined the overall system structure. This included the main modules, data flow, crawl lifecycle, search lifecycle, persistence expectations, and system boundaries.

It was also responsible for making the major technical tradeoffs, such as:

- Python-based localhost design
- SQLite for local persistence
- bounded queue and fixed worker count for backpressure
- keyword-based relevance instead of semantic search
- eventual consistency for search during active indexing

Without this agent, the project would risk becoming a collection of disconnected implementation decisions.

---

### 4.2 Crawl Engineer Agent

The Crawl Engineer Agent owned the operational crawler logic. Its responsibility was to ensure that the `index` function satisfied the assignment exactly.

This included:

- starting from an origin URL
- enforcing maximum depth `k`
- recursively discovering links
- preventing duplicate crawling
- handling failures safely
- working within bounded queue constraints
- exposing crawl progress and queue state

This agent focused on correctness and controlled execution rather than on storage design or search relevance.

---

### 4.3 Storage Engineer Agent

The Storage Engineer Agent owned the persistent model of the system. Its job was to make sure all important state could be stored locally and reused consistently.

This included:

- crawl run records
- frontier state
- duplicate prevention support
- page records
- searchable term storage
- indexing state
- optional resume support

This role mattered because a crawler and search engine both depend heavily on stable state management. It also became the main support for partial visibility when search is run during indexing.

---

### 4.4 Index and Search Engineer Agent

The Index and Search Engineer Agent owned the transformation from crawled pages into searchable results.

Its responsibilities were:

- tokenizing text
- storing term frequencies
- matching query terms to indexed pages
- computing relevance scores
- returning results in the required triple format:
  `(relevant_url, origin_url, depth)`

This agent intentionally used a lightweight and explainable relevance model rather than a large external search framework. That decision kept the project aligned with the assignment’s preference for native functionality and reasonable assumptions.

---

### 4.5 QA Reviewer Agent

The QA Reviewer Agent acted as the validation layer for the whole workflow. Its job was not to write the implementation, but to challenge it.

It checked:

- whether crawl depth was handled correctly
- whether duplicate crawling was truly prevented
- whether failures were isolated
- whether storage state transitions were coherent
- whether search outputs were correct
- whether documentation matched the actual system

This agent prevented the project from drifting into “it seems to work” territory.

---

### 4.6 Documentation and Integration Agent

The Documentation and Integration Agent turned the technical outputs into a coherent submission. It produced and aligned the explanation files so the repository could be reviewed without confusion.

This included:

- writing the workflow explanation
- finalizing agent files
- helping align README and recommendation text
- making sure technical claims remained realistic
- ensuring that the project clearly satisfied the multi-agent requirement through the development process

This role mattered because a good implementation can still be graded badly if the reasoning and structure are not explained well.

---

## 5. How the Agents Interacted

The agents did not operate in a random or equal-access manner. Their interactions followed a structured flow.

### Phase 1: Architecture First

The Architect Agent started by converting the assignment into an implementation plan. It defined:

- the system components
- their boundaries
- core data flow
- storage expectations
- search expectations
- backpressure approach
- how the system could support search during active indexing

This phase was necessary because the later agents needed a stable blueprint.

---

### Phase 2: Specialist Design and Implementation Ownership

Once the blueprint existed, the work was split:

- Crawl Engineer Agent developed the crawling model.
- Storage Engineer Agent developed the persistence model.
- Index and Search Engineer Agent developed the indexing and retrieval model.

These agents worked with the same architecture but from different angles. They also depended on each other. For example:

- crawl needed storage to persist frontier state
- search needed storage to preserve origin and depth
- storage needed crawl and search to define what fields were actually required

This made collaboration necessary rather than cosmetic.

---

### Phase 3: QA Review

The QA Reviewer Agent then inspected the outputs of the specialist agents. It checked whether the system matched the actual assignment rather than just whether each component looked reasonable in isolation.

This review step was especially important for catching:

- off-by-one depth mistakes
- duplicate URL handling gaps
- unclear indexing state transitions
- search results that did not preserve `origin_url` and `depth`

The QA phase created a formal correction loop before completion.

---

### Phase 4: Documentation and Final Integration

After the technical parts were stabilized, the Documentation and Integration Agent gathered the design rationale and final decisions into submission-ready documents.

This stage ensured:

- consistency across files
- credible explanation of the multi-agent workflow
- realistic production recommendation
- clear mapping between implementation and assignment requirements

This final phase made the project understandable to reviewers.

---

## 6. Communication Model Between Agents

The workflow followed a contract-based communication model.

Each agent received:

- defined inputs
- a bounded problem area
- required outputs
- completion conditions

Agents did not overwrite each other’s roles casually. Instead, they exchanged structured outputs.

Examples:

- The Architect Agent gave the Crawl Engineer Agent a crawl model and depth definition.
- The Crawl Engineer Agent gave the Storage Engineer Agent required frontier states.
- The Storage Engineer Agent gave the Search Engineer Agent page and term storage guarantees.
- The QA Reviewer Agent returned failure reports and missing-case findings.
- The Documentation Agent recorded only the decisions that were actually accepted.

This made the workflow easier to reason about and easier to explain.

---

## 7. Decision-Making Strategy

When agents proposed different directions, decisions were made using the following order of priority:

1. assignment correctness
2. architectural clarity
3. simplicity of localhost execution
4. explainability during grading
5. performance within reasonable scope

This priority order is why certain design choices were made.

### Example 1: SQLite Instead of a Heavier DB

SQLite was selected because:

- localhost execution was required
- setup needed to stay simple
- the project did not need distributed DB features
- the design remained easy to explain

### Example 2: Bounded Queue Instead of Complex Scheduling

A bounded frontier queue and fixed worker count were selected because:

- the assignment explicitly asked for backpressure
- this approach clearly satisfies that requirement
- it is simple enough to implement correctly
- it is easy to monitor and justify

### Example 3: Term-Based Search Instead of Semantic Search

Keyword-based ranking was selected because:

- the assignment only asked for relevant URLs, not advanced semantic search
- native or near-native implementation was preferred
- external search engines would solve too much out of the box
- the scoring could be explained transparently

### Example 4: Eventual Consistency for Search During Indexing

The system was designed so search could run while indexing is active by exposing only already indexed pages.

This choice was made because:

- it supports the teacher’s expected discussion point
- it avoids strict consistency complexity
- it fits SQLite and local execution
- it is realistic for a crawler/search pipeline

---

## 8. Quality Control Process

The workflow used output evaluation as an explicit step, not as an afterthought.

Each major output was checked against:

- assignment wording
- agent-specific scope
- downstream dependency needs
- likely demo questions from instructors

The QA Reviewer Agent was the formal validation point, but quality control also happened through dependency pressure. For example:

- if storage did not preserve depth, search could not return the required triple
- if crawl logic did not normalize URLs, duplicate prevention could fail
- if documentation exaggerated the system, the repo would become hard to defend

This forced decisions to stay grounded.

---

## 9. How Agent Outputs Were Managed

Agent outputs were managed in a staged way rather than all at once.

### 9.1 Structured Role Files

Each agent was documented in its own `.md` file containing:

- mission
- responsibilities
- inputs
- outputs
- constraints
- collaboration rules
- done criteria

This made the workflow inspectable.

### 9.2 Shared Design Vocabulary

To avoid confusion, the workflow used stable terms across all agents:

- origin URL
- max depth
- frontier
- crawl run
- indexed page
- backpressure
- eventual consistency

This reduced ambiguity across design and documentation.

### 9.3 Review Before Finalization

An output was not treated as complete just because an agent had produced it. The QA Reviewer Agent and Documentation Agent both checked whether that output was consistent with the rest of the system.

---

## 10. Why This Workflow Is a Good Fit for the Assignment

This workflow matches the assignment well because the project itself naturally breaks into technical concerns that are easy to assign to separate agents.

The assignment asked the team to:

- define agents
- assign responsibilities
- decide interactions
- manage and evaluate outputs

This workflow does exactly that in a way that is technically justified. It does not force artificial runtime agents into the actual software. Instead, it uses specialized development agents to produce a cleaner and more accountable design process.

That is a better fit for the wording:
“The final system does not need to be implemented as a multi-agent runtime. The requirement is that your development process demonstrates clear multi-agent collaboration.”

---

## 11. Strengths of This Workflow

The chosen workflow had several strengths:

- clear separation of concerns
- better traceability of decisions
- easier debugging of design mistakes
- formal review before completion
- good alignment with the required deliverables
- easier explanation during presentation or grading

Most importantly, it reduced the chance of building the wrong thing quickly.

---

## 12. Weaknesses and Tradeoffs

This workflow also had costs.

- It introduced some overhead in documenting responsibilities.
- It required more discipline than a single-agent rapid coding approach.
- There was some duplication in decision explanation across architecture and documentation phases.
- Since the actual system is localhost-scale, the workflow is more formal than strictly necessary for a tiny solo script.

These tradeoffs were accepted because the assignment explicitly values architectural sensibility and workflow quality, not only raw implementation speed.

---

## 13. Final Outcome

The final outcome of the workflow is a Python-based crawler and search engine designed for localhost execution with persistent crawl state, bounded crawling behavior, incremental indexing, and keyword-based search.

The agent workflow shaped both the implementation and the documentation. It ensured that:

- the crawler obeys depth and duplicate constraints
- the storage model supports both indexing and search
- the search output preserves required crawl metadata
- the system can be explained as supporting concurrent search through incremental indexed visibility
- the repository contains explicit evidence of multi-agent development

This directly satisfies the assignment’s expectations for functionality, scalability reasoning, architectural sensibility, and workflow clarity.

---

## 14. Conclusion

The multi-agent workflow in this project was used as a design and management strategy rather than as a runtime execution model. That choice was deliberate and aligned with the assignment.

Each agent had a clear role, specific responsibilities, and concrete outputs. Their interactions were staged and review-driven. The result is a final project that is not only functional, but also structurally defensible and clearly documented.

That is the real value of the workflow: it turned a potentially messy from-scratch implementation into a controlled engineering process.
