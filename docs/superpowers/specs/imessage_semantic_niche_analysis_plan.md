# Plan: Discovering Latent Structure in a Personal iMessage Corpus

## 0. Objective

Build an analysis pipeline over a personal iMessage archive to answer:

> What semantic niches, recurring conversational modes, relationship-specific topics, and temporal patterns exist across my conversations?

The corpus is **ego-centric**: every conversation is between me and one contact or group thread. Contacts are not assumed to know one another. Any graph connecting contacts means only that my conversations with them are similar in some measurable way.

The central technical problem is not visualization. It is constructing a representation in which meaningful, low-frequency niches are separable from generic conversational language such as “like,” “bro,” “yeah,” “lol,” and logistical filler.

The system should recover structure at several scales:

1. broad life domains;
2. narrow semantic niches;
3. conversation functions;
4. relationship archetypes;
5. temporal shifts;
6. unusual local patterns that do not form large global clusters.

---

# 1. Existing Inputs and Assumptions

Assume the application already contains:

- one embedding per message, contact, or both;
- timestamps;
- sender direction: `me -> contact` or `contact -> me`;
- conversation or thread identifiers;
- contact identifiers;
- basic activity analytics;
- message text.

The pipeline should reuse existing embeddings rather than recomputing everything initially.

Recommended canonical records:

```text
Message
- message_id
- thread_id
- contact_id or group_thread_id
- timestamp
- direction
- text
- embedding
- reply metadata, if available
```

Derived units:

```text
Session
- session_id
- thread_id
- start_time
- end_time
- ordered message_ids
- session_embedding
- information_weight
```

```text
ContactPeriod
- contact_id
- period_start
- period_end
- topic distribution
- function distribution
- behavioral statistics
```

---

# 2. First Principle: Do Not Treat Every Message Equally

Individual iMessages are often semantically incomplete:

- “yeah”
- “that’s insane”
- “bro”
- “what time”
- “I’m down”
- “send it”

These messages contain relational or conversational information but very little standalone topical information.

The pipeline should distinguish between:

## 2.1 Content-bearing messages

Messages with enough information to identify a topic, entity, claim, event, or activity.

## 2.2 Context-bearing messages

Short replies that reveal agreement, affect, pacing, reciprocity, humor, or conversational function, but not subject matter.

## 2.3 Low-information filler

Messages that add almost no semantic or behavioral information.

Define an information weight:

\[
q_i \in [0,1]
\]

for message \(i\). A practical initial approximation can combine:

\[
q_i =
\sigma\left(
a_0
+ a_1 \log(1+\text{tokens}_i)
+ a_2 \cdot \text{content\_word\_ratio}_i
+ a_3 \cdot \text{entity\_count}_i
+ a_4 \cdot \text{embedding\_novelty}_i
\right)
\]

where \(\sigma\) is a logistic transform.

Use \(q_i\) to:

- weight session embeddings;
- suppress filler in cluster labels;
- avoid creating graph hubs from generic language;
- retain short messages for behavioral analysis without letting them dominate semantic analysis.

Do not permanently discard low-information messages. They may be useful later for interaction style and reciprocity.

---

# 3. Sessionization

## 3.1 Why sessions should be the main semantic unit

A session contains enough context to disambiguate short messages while preserving local conversational meaning. Message-level clustering is still useful for edge cases, but session-level analysis should be the default.

A session is a maximal sequence of messages in one thread such that consecutive messages are separated by less than an inactivity threshold \(\tau\).

Initial threshold candidates:

- 2 hours;
- 4 hours;
- 8 hours;
- adaptive threshold based on thread-specific gap distributions.

A more principled method is to fit a two-component mixture model to log inter-message gaps:

\[
\log \Delta t \sim
\pi \mathcal{N}(\mu_{\text{within}}, \sigma_{\text{within}}^2)
+
(1-\pi)\mathcal{N}(\mu_{\text{between}}, \sigma_{\text{between}}^2)
\]

Choose the threshold near the intersection of the two fitted densities.

This estimates the boundary between:

- pauses within one conversation;
- breaks between distinct conversations.

## 3.2 Session embedding

If message embeddings already exist, compute:

\[
z_s =
\frac{\sum_{i \in s} q_i \ell_i^\beta z_i}
{\sum_{i \in s} q_i \ell_i^\beta}
\]

where:

- \(z_i\) is the normalized embedding of message \(i\);
- \(q_i\) is information weight;
- \(\ell_i\) is message length;
- \(\beta \in [0,0.5]\) prevents long messages from overwhelming the session.

Normalize \(z_s\) afterward.

Alternative representations to compare:

1. weighted mean of message embeddings;
2. direct embedding of concatenated session text;
3. embedding of an automatically generated session summary;
4. concatenation or fusion of:
   - semantic embedding;
   - conversation-function embedding;
   - behavioral features.

Start with the weighted mean because it reuses existing work and is easy to audit.

---

# 4. Build the Semantic Neighborhood Graph

Let each session be a node.

A dense all-pairs similarity graph is unnecessary and will be noisy. Construct a sparse neighborhood graph.

## 4.1 Similarity

For normalized embeddings:

\[
s_{ij} = z_i^\top z_j
\]

Do not immediately use raw cosine similarity as an edge weight. The local density of embedding space varies, so the same cosine similarity may be strong in one region and weak in another.

## 4.2 Mutual k-nearest-neighbor graph

Connect \(i\) and \(j\) only when:

\[
i \in \operatorname{kNN}(j)
\quad \text{and} \quad
j \in \operatorname{kNN}(i)
\]

Mutual k-NN suppresses accidental one-sided neighbors and reduces hubness.

Evaluate:

\[
k \in \{10, 15, 20, 30, 50\}
\]

Smaller \(k\):

- exposes narrow niches;
- creates disconnected fragments;
- is more sensitive to noise.

Larger \(k\):

- improves connectivity;
- smooths over small niches;
- may merge distinct semantic regions.

## 4.3 Adaptive local scaling

Use a self-tuning kernel rather than one global bandwidth:

\[
w_{ij}
=
\exp\left(
-\frac{d_{ij}^2}{\sigma_i \sigma_j}
\right)
\]

where:

\[
d_{ij} = 1 - s_{ij}
\]

and \(\sigma_i\) is the distance from \(i\) to its \(k_\sigma\)-th neighbor.

This adapts the graph to local density and is preferable when some conversational topics are dense and repetitive while others are sparse and specialized.

## 4.4 Optional metadata-aware edge terms

The base graph should be semantic. Add metadata only as controlled secondary terms.

A possible composite edge:

\[
\tilde w_{ij}
=
w_{ij}
\cdot
(1 + \alpha T_{ij})
\cdot
(1 + \beta C_{ij})
\]

where:

- \(T_{ij}\) represents temporal proximity;
- \(C_{ij}\) indicates same contact or thread;
- \(\alpha,\beta\) should be small.

Run the pipeline first with \(\alpha=\beta=0\). Otherwise, the graph may recover contact identity or chronology rather than semantic structure.

Contact and time should usually be analyzed as **signals on the graph**, not baked into the graph itself.

---

# 5. Graph Laplacians and Spectral Representation

Given adjacency matrix \(W\), define degree matrix:

\[
D_{ii} = \sum_j W_{ij}
\]

Candidate Laplacians:

## 5.1 Unnormalized Laplacian

\[
L = D-W
\]

Useful theoretically but sensitive to degree variation.

## 5.2 Symmetric normalized Laplacian

\[
L_{\mathrm{sym}}
=
I-D^{-1/2}WD^{-1/2}
\]

Recommended default for spectral clustering.

## 5.3 Random-walk Laplacian

\[
L_{\mathrm{rw}}
=
I-D^{-1}W
\]

Useful when interpreting the graph as a Markov chain.

Compute the smallest eigenpairs:

\[
0=\lambda_1 \le \lambda_2 \le \cdots
\]

The corresponding eigenvectors provide global coordinates of semantic structure.

Interpretation:

- low-frequency eigenvectors vary slowly across strong semantic edges;
- they capture broad semantic divisions and smooth manifold directions;
- higher-frequency eigenvectors capture smaller or more rapidly changing local structure.

---

# 6. Spectral Clustering

## 6.1 Basic method

For candidate cluster count \(K\):

1. compute the first \(K\) eigenvectors of \(L_{\mathrm{sym}}\);
2. stack them into matrix \(U \in \mathbb{R}^{n \times K}\);
3. normalize each row of \(U\);
4. run k-means or a mixture model on the rows.

The row for session \(i\) is its spectral embedding.

## 6.2 Eigengap heuristic

Estimate \(K\) by examining:

\[
g_k = \lambda_{k+1} - \lambda_k
\]

A large \(g_k\) suggests that the first \(k\) eigenvectors form a stable low-dimensional subspace.

Do not use the largest eigengap blindly. In conversational data, the spectrum may be smooth because topic structure is hierarchical and overlapping.

Use eigengaps as one signal among:

- cluster stability;
- conductance;
- semantic coherence;
- persistence across graph parameters;
- interpretability.

## 6.3 Recursive spectral partitioning

For a hierarchy, recursively split a cluster using its Fiedler vector, the eigenvector corresponding to the second-smallest eigenvalue.

For subgraph \(G_C\):

1. compute its Fiedler vector \(v_2\);
2. propose a split by sign or by sweeping thresholds over sorted \(v_2\);
3. choose the threshold minimizing normalized cut;
4. accept the split only if it improves quality and both children are sufficiently large.

Normalized cut:

\[
\operatorname{Ncut}(A,B)
=
\frac{\operatorname{cut}(A,B)}{\operatorname{vol}(A)}
+
\frac{\operatorname{cut}(A,B)}{\operatorname{vol}(B)}
\]

This is suitable for producing:

```text
work
  engineering
    retrieval systems
    integrations
  company strategy
personal
  fitness
  nightlife
  relationships
```

Recursive splitting is often more natural for a personal corpus than selecting one global \(K\).

---

# 7. Diffusion Maps

Spectral clustering emphasizes partitions. Diffusion maps recover continuous semantic geometry.

Define transition matrix:

\[
P = D^{-1}W
\]

The \(t\)-step transition probability \(P^t_{ij}\) measures how easily a random walk moves from session \(i\) to session \(j\).

Diffusion distance:

\[
D_t^2(i,j)
=
\sum_k
\frac{
(P^t_{ik}-P^t_{jk})^2
}{
\phi_0(k)
}
\]

where \(\phi_0\) is the stationary distribution.

Using eigenpairs of \(P\):

\[
\Psi_t(i)
=
\left(
\lambda_1^t \psi_1(i),
\lambda_2^t \psi_2(i),
\ldots,
\lambda_m^t \psi_m(i)
\right)
\]

This embedding suppresses short, noisy edges and emphasizes multi-step semantic connectivity.

Interpretation of scale \(t\):

- small \(t\): fine local distinctions;
- medium \(t\): stable semantic neighborhoods;
- large \(t\): broad life domains.

Questions diffusion maps help answer:

- Are topics discrete clusters or smooth transitions?
- Which conversations sit between work and personal life?
- Which semantic paths connect two otherwise distinct niches?
- Does one apparent cluster contain an internal continuum?

Use diffusion coordinates as:

- an alternative representation for clustering;
- a way to identify bridges;
- a multiscale view of the corpus.

---

# 8. Multi-Resolution Community Detection

Use Leiden on the semantic graph as a graph-native complement to spectral clustering.

A common objective is modularity with resolution parameter \(\gamma\):

\[
Q(\gamma)
=
\frac{1}{2m}
\sum_{ij}
\left(
W_{ij}
-
\gamma \frac{d_i d_j}{2m}
\right)
\mathbf{1}[c_i=c_j]
\]

Larger \(\gamma\) produces smaller communities.

Run a resolution sweep, for example:

\[
\gamma \in
\{0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5\}
\]

Do not choose one resolution immediately. Track how communities split and merge across \(\gamma\).

Construct a cluster lineage graph:

```text
broad cluster at gamma 0.5
        |
        +-- niche A at gamma 1.5
        +-- niche B at gamma 1.5
                 |
                 +-- subniche B1 at gamma 3
                 +-- subniche B2 at gamma 3
```

A niche is more credible when it:

- appears across several adjacent resolutions;
- has stable membership;
- has low conductance;
- has coherent representative sessions;
- survives modest graph perturbations.

---

# 9. Local Niche Discovery

Large global methods tend to privilege dominant topics. The goal is also to find small, dense, unusual regions.

## 9.1 Local conductance

For candidate set \(S\):

\[
\phi(S)
=
\frac{\operatorname{cut}(S,\bar S)}
{\min(\operatorname{vol}(S), \operatorname{vol}(\bar S))}
\]

Low conductance indicates a group strongly connected internally and weakly connected externally.

Search for low-conductance neighborhoods around seed nodes using:

- personalized PageRank;
- sweep cuts;
- local spectral methods.

## 9.2 Personalized PageRank

For seed distribution \(s\):

\[
p =
\alpha s + (1-\alpha)P^\top p
\]

The resulting vector ranks nodes by diffusion proximity to the seed.

Procedure:

1. choose an interesting or unusual session;
2. compute personalized PageRank;
3. sort nodes by \(p_i/d_i\);
4. sweep prefixes;
5. select the prefix with minimum conductance.

This can recover a niche that is too small to become a global cluster.

## 9.3 Local outlier factor in spectral or diffusion space

Compute local density deviation:

\[
\operatorname{LOF}_k(i)
=
\frac{
\text{average local reachability density of neighbors}
}{
\text{local reachability density of } i
}
\]

Use it to find:

- semantically unusual sessions;
- rare topics;
- abrupt topic shifts;
- extraction or embedding failures.

High outlier score is not automatically interesting. It may reflect malformed text, URLs, or one-off logistics.

---

# 10. Graph Wavelets for Localized Semantic Structure

Global Laplacian eigenvectors resemble graph-wide Fourier modes. They identify broad smooth patterns but are not localized.

A spectral graph wavelet centered at node \(i\) and scale \(s\) can be written:

\[
\psi_{s,i}
=
g(sL)\delta_i
\]

Using the eigendecomposition \(L=U\Lambda U^\top\):

\[
\psi_{s,i}
=
U g(s\Lambda) U^\top \delta_i
\]

where:

- \(\delta_i\) is an impulse at session \(i\);
- \(g\) is a band-pass spectral kernel;
- \(s\) controls scale.

Interpretation:

- small scale: immediate, highly specific semantic neighborhood;
- medium scale: niche topic;
- large scale: broader domain.

A wavelet coefficient for graph signal \(f\) is:

\[
W_f(s,i)
=
\langle f,\psi_{s,i}\rangle
\]

Possible graph signals:

- indicator that a message is yours;
- activity date;
- response latency;
- emotional valence;
- contact identity;
- question rate;
- technicality;
- extracted entity presence.

This allows localized questions such as:

- Around this niche, which contacts are overrepresented?
- Is this local semantic region recent or old?
- Is this topic mostly initiated by me or by others?
- Does a specific emotional or conversational pattern occur only in this neighborhood?
- At what semantic scale does the pattern appear?

Graph wavelets are most valuable after the base graph is trustworthy. They are not a replacement for clustering; they expose local structure that global partitions blur.

---

# 11. Graph Signal Processing

Once the semantic graph exists, treat metadata as signals over its nodes.

For a scalar node attribute \(f \in \mathbb{R}^n\), graph Fourier transform:

\[
\hat f = U^\top f
\]

Inverse transform:

\[
f = U\hat f
\]

Graph smoothness:

\[
f^\top L f
=
\frac{1}{2}
\sum_{ij} W_{ij}(f_i-f_j)^2
\]

Low smoothness means the attribute is similar among semantically neighboring sessions.

Examples:

## 11.1 Contact identity as a graph signal

For each contact \(c\), define:

\[
f_c(i)=
\begin{cases}
1 & \text{session } i \text{ involves } c\\
0 & \text{otherwise}
\end{cases}
\]

If \(f_c^\top Lf_c\) is low, conversations with that person occupy a coherent semantic region.

If high, the relationship spans many unrelated domains.

## 11.2 Time as a graph signal

Map timestamp to a normalized scalar. If time is smooth over a niche, that topic may belong to a specific life period.

## 11.3 Direction as a graph signal

Encode whether the session is initiated by you or by the contact. Local smoothness can reveal topics systematically initiated by one side.

## 11.4 Low-pass filtering

\[
f_{\text{smooth}}
=
h(L)f
\]

where \(h\) suppresses high graph frequencies.

This denoises noisy behavioral metrics over semantic neighborhoods.

---

# 12. Contact–Niche Bipartite Structure

Once semantic niches are discovered, create a contact-by-niche matrix \(B\).

\[
B_{ct}
=
\sum_{i:
\operatorname{contact}(i)=c}
q_i \cdot r_{it}
\]

where \(r_{it}\) is session \(i\)'s membership or probability for niche \(t\).

Normalize in multiple ways:

## 12.1 Within-contact distribution

\[
P(t\mid c)
=
\frac{B_{ct}}{\sum_{t'}B_{ct'}}
\]

Answers: what proportion of my relationship with this person concerns each niche?

## 12.2 Within-topic distribution

\[
P(c\mid t)
=
\frac{B_{ct}}{\sum_{c'}B_{c't}}
\]

Answers: who do I primarily discuss this niche with?

## 12.3 TF-IDF-like contact-topic weighting

\[
\operatorname{ctfidf}(c,t)
=
P(t\mid c)
\cdot
\log
\frac{N_{\text{contacts}}}
{1+\#\{c':B_{c't}>0\}}
\]

This emphasizes topics characteristic of a relationship rather than common across everyone.

## 12.4 Spectral co-clustering

Construct normalized matrix:

\[
\tilde B
=
D_c^{-1/2}BD_t^{-1/2}
\]

Compute a truncated SVD:

\[
\tilde B = U\Sigma V^\top
\]

Rows of \(U\) embed contacts; rows of \(V\) embed niches in a shared latent structure.

This can reveal blocks such as:

```text
set of contacts
    <->
set of related conversation niches
```

The contacts are not socially connected. They are grouped because they occupy similar roles in your message corpus.

---

# 13. Contrastive Phrase and Entity Labeling

Graph methods identify structure; they do not automatically provide good names.

Do not rank raw unigram frequency.

## 13.1 Weighted log odds with an informative prior

For term \(w\) in cluster \(C\):

\[
\delta_w
=
\log
\frac{y_{w,C}+\alpha_w}
{n_C+\alpha_0-y_{w,C}-\alpha_w}
-
\log
\frac{y_{w,\neg C}+\alpha_w}
{n_{\neg C}+\alpha_0-y_{w,\neg C}-\alpha_w}
\]

Approximate variance:

\[
\sigma^2(\delta_w)
\approx
\frac{1}{y_{w,C}+\alpha_w}
+
\frac{1}{y_{w,\neg C}+\alpha_w}
\]

Standardized score:

\[
z_w =
\frac{\delta_w}{\sqrt{\sigma^2(\delta_w)}}
\]

This identifies terms disproportionately associated with the cluster while controlling rare-count noise.

## 13.2 Jensen–Shannon divergence contribution

For each term, measure how much it contributes to the difference between cluster and background language distributions.

## 13.3 Phrase units

Prefer:

- noun phrases;
- named entities;
- project names;
- company names;
- locations;
- activity phrases;
- recurring multiword expressions.

Suppress:

- generic conversational tokens;
- platform artifacts;
- names used merely as salutations;
- sender-specific catchphrases unless analyzing style.

## 13.4 Sender-baseline correction

A phrase may be distinctive only because one person says it frequently.

Estimate:

\[
\operatorname{score}(w,C)
=
\operatorname{cluster\_contrast}(w,C)
-
\lambda
\operatorname{sender\_specificity}(w)
\]

This separates subject matter from personal verbal habits.

## 13.5 Representative sessions

For cluster centroid \(\mu_C\), select central examples:

\[
i^*
=
\arg\max_{i \in C}
\cos(z_i,\mu_C)
\]

Also include boundary examples and high-information examples. Cluster labels should always be auditable against source sessions.

---

# 14. Stability and Persistence

Do not trust one clustering run.

## 14.1 Bootstrap stability

Repeatedly sample sessions or edges, rebuild the graph, and recluster.

Compare clusterings using:

- adjusted Rand index;
- normalized mutual information;
- variation of information.

For cluster \(C\), compute membership stability using maximum Jaccard overlap with clusters in perturbed runs.

## 14.2 Parameter persistence

Vary:

- \(k\) in k-NN;
- local bandwidth;
- Leiden resolution;
- session threshold;
- embedding representation;
- inclusion or exclusion of short messages.

A niche is credible when a similar group appears across nearby parameter settings.

## 14.3 Temporal persistence

Determine whether a niche:

- persists over long periods;
- appears only during one event;
- recurs episodically;
- grows or declines.

Rare but temporally coherent niches may be more meaningful than large diffuse clusters.

---

# 15. Evaluation Metrics

No single clustering metric captures “interestingness.”

Use a scorecard.

## 15.1 Structural metrics

### Conductance

Lower is better for separation.

### Modularity contribution

Measures excess internal edge mass relative to a null model.

### Internal density

\[
\rho(C)
=
\frac{\sum_{i,j\in C}W_{ij}}
{|C|(|C|-1)}
\]

### Spectral gap within subgraph

A large internal gap can indicate stable substructure.

## 15.2 Semantic metrics

### Coherence

Average pairwise similarity among high-information sessions.

### Distinctiveness

Divergence between cluster phrase distribution and corpus background.

### Representative consistency

Whether top representative sessions clearly support the cluster interpretation.

## 15.3 Stability metrics

- bootstrap Jaccard;
- ARI/NMI across runs;
- persistence across graph parameters;
- persistence across resolutions.

## 15.4 Personal-interest metrics

A useful niche may be:

- small but highly distinctive;
- concentrated in one relationship;
- spread across otherwise unrelated contacts;
- temporally localized;
- a bridge between major life domains;
- unusually associated with your outgoing or incoming messages.

Define an exploratory niche score:

\[
I(C)
=
a \cdot \operatorname{stability}(C)
+
b \cdot \operatorname{distinctiveness}(C)
+
c \cdot (1-\operatorname{conductance}(C))
+
d \cdot \operatorname{surprisal}(C)
+
e \cdot \operatorname{temporal\_coherence}(C)
\]

Weights should be tuned by manual inspection, not treated as universal constants.

---

# 16. Bridge and Boundary Analysis

Some of the most interesting sessions will not be central to any cluster.

## 16.1 Participation coefficient

Given communities \(1,\ldots,K\):

\[
P_i
=
1-
\sum_{c=1}^K
\left(
\frac{k_{ic}}{k_i}
\right)^2
\]

High \(P_i\) means node \(i\) connects multiple communities.

## 16.2 Betweenness centrality

\[
BC(i)
=
\sum_{s\neq i\neq t}
\frac{\sigma_{st}(i)}
{\sigma_{st}}
\]

Use cautiously on large graphs and weighted semantic distances.

Bridge sessions may reveal:

- transitions between personal and professional contexts;
- people who span multiple life domains;
- themes connecting otherwise separate niches;
- conversations where one topic evolves into another.

## 16.3 Diffusion-based boundary score

Compare a node’s diffusion affinity to multiple communities. Nodes with similar affinity to two communities lie on semantic boundaries.

---

# 17. Temporal Niche Dynamics

Create time-window-specific topic weights.

For niche \(C\) and period \(t\):

\[
a_{C,t}
=
\sum_{i \in C,\, \operatorname{time}(i)=t}
q_i
\]

Normalize either by total corpus activity in period \(t\) or by contact activity.

Detect change points using:

- Bayesian online change-point detection;
- PELT;
- cumulative sum methods;
- Jensen–Shannon divergence between consecutive topic distributions.

For contact \(c\):

\[
D_{\mathrm{JS}}
\left(
P_t(\text{topic}\mid c),
P_{t+1}(\text{topic}\mid c)
\right)
\]

Large divergence indicates a change in relationship content.

Track whether niches:

- emerge;
- split;
- merge;
- disappear;
- transfer from one contact to another;
- become more or less concentrated socially.

---

# 18. Recommended Experimental Sequence

## Experiment 1: Validate the semantic unit

Compare:

- raw message graph;
- session graph;
- contact-period graph.

Manual evaluation:

- inspect 100 nearest-neighbor pairs for each representation;
- rate semantic agreement;
- record failure modes.

Expected result: session embeddings should outperform raw messages for topic discovery.

## Experiment 2: Graph construction sweep

For each:

\[
k \in \{10,15,20,30,50\}
\]

compare:

- ordinary k-NN;
- mutual k-NN;
- adaptive local scaling;
- cosine threshold graph.

Measure:

- giant component size;
- degree distribution;
- hubness;
- neighbor quality;
- niche retention.

Default candidate: mutual k-NN with adaptive local scaling.

## Experiment 3: Global structure

Run:

- normalized spectral clustering;
- recursive Fiedler partitioning;
- Leiden resolution sweep;
- HDBSCAN in embedding space as a non-graph baseline.

Compare:

- stability;
- conductance;
- interpretability;
- ability to recover small niches.

## Experiment 4: Diffusion geometry

Compute diffusion maps at several \(t\).

Test whether:

- semantic bridges become clearer;
- broad domains separate more cleanly;
- clusters become more stable;
- continuous axes appear where hard clustering was misleading.

## Experiment 5: Local niche mining

Select seeds from:

- high-LOF sessions;
- manually interesting messages;
- weakly assigned cluster boundary points;
- rare phrase hits.

Run personalized PageRank plus conductance sweeps.

Evaluate whether these local communities recover meaningful niche themes missed by global clustering.

## Experiment 6: Wavelet analysis

Choose graph signals:

- contact indicators;
- message direction;
- time;
- emotional valence;
- question rate.

Compute wavelet coefficients across scales.

Look for localized concentrations such as:

- one niche dominated by a small set of contacts;
- an old niche that disappears;
- a topic mostly initiated by others;
- a local emotional or behavioral signature.

## Experiment 7: Contact–niche structure

Construct \(B_{ct}\), normalize it, and run:

- SVD;
- spectral co-clustering;
- non-negative matrix factorization as a baseline.

Interpret latent dimensions and contact-topic blocks.

---

# 19. Practical Initial Configuration

Use this as a first implementation, not as a final truth.

```text
Semantic unit:
- conversation sessions

Session boundary:
- adaptive threshold from inter-message-gap mixture
- fallback: 4 hours

Graph:
- mutual 20-NN
- cosine distance
- adaptive local scaling using 10th neighbor

Graph pruning:
- remove edges below local similarity quantile
- retain enough edges for a large connected component

Global discovery:
- Leiden resolution sweep
- recursive spectral partitioning
- diffusion map coordinates

Local discovery:
- personalized PageRank
- conductance sweep
- LOF in diffusion space

Labeling:
- noun phrases + named entities
- weighted log odds against corpus background
- sender-baseline penalty
- representative session retrieval

Evaluation:
- bootstrap stability
- parameter persistence
- conductance
- semantic coherence
- manual review
```

---

# 20. Minimal Deliverables

The mathematical pipeline is successful when it produces:

## 20.1 Multi-scale niche catalog

For every niche:

```text
- niche_id
- parent_niche_id
- scale or resolution
- member sessions
- defining phrases and entities
- representative sessions
- conductance
- stability
- temporal activity
- contact distribution
```

## 20.2 Contact–niche matrix

Both all-time and time-dependent.

## 20.3 Bridge-session table

Sessions connecting multiple semantic domains.

## 20.4 Local niche search

Given one seed message or session, return its lowest-conductance semantic neighborhood.

## 20.5 Spectral diagnostics

Store:

- eigenvalues;
- eigengaps;
- spectral embeddings;
- diffusion coordinates;
- graph parameter settings;
- cluster stability metrics.

These diagnostics are necessary to understand why a niche exists and whether it is robust.

---

# 21. Important Failure Modes

## 21.1 Contact leakage

Clusters become person-specific rather than semantically meaningful.

Mitigation:

- do not include contact identity in the base similarity graph;
- inspect contact entropy within clusters;
- compare with contact-shuffled baselines.

## 21.2 Time leakage

Clusters recover life periods rather than topics.

Mitigation:

- exclude timestamps from the base graph;
- analyze time afterward as a graph signal;
- inspect temporal concentration.

## 21.3 Generic conversational hubs

Messages like “yeah,” “lol,” and “bro” connect unrelated regions.

Mitigation:

- sessionization;
- information weighting;
- mutual k-NN;
- adaptive local scaling;
- remove or downweight low-information nodes for semantic analysis.

## 21.4 Embedding hubness

A small number of generic sessions appear in many neighbor lists.

Mitigation:

- mutual k-NN;
- local scaling;
- shared-nearest-neighbor similarity;
- hubness diagnostics.

Shared-nearest-neighbor similarity:

\[
\operatorname{SNN}(i,j)
=
|\operatorname{kNN}(i)\cap \operatorname{kNN}(j)|
\]

This can replace or complement cosine weights.

## 21.5 Forced hard clusters

Many sessions legitimately belong to multiple topics.

Mitigation:

- retain soft memberships;
- use diffusion coordinates;
- use overlapping community methods or topic mixtures;
- treat boundary points explicitly.

## 21.6 Attractive but unstable niches

A cluster looks interesting in one run but disappears under small perturbations.

Mitigation:

- bootstrap;
- resolution persistence;
- graph-parameter sweeps;
- minimum stability threshold.

---

# 22. Final Research Question

The final system should make the following question empirically tractable:

> Across all of my conversations, what semantic regions exist; which are broad domains versus narrow niches; which people and periods occupy them; which themes bridge otherwise separate parts of my life; and which patterns remain stable across graph scales rather than appearing as artifacts of one clustering choice?

The graph is not the end product. It is the mathematical object that converts the embedding space into a structure on which global partitions, local neighborhoods, diffusion geometry, graph frequencies, and multiscale niche persistence can be measured.
