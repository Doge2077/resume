检索增强生成（Retrieval-Augmented Generation， RAG）
开放域问答（Open domain question answering，ODQA）是自然语言处理（NLP）中一个长期存在待解决的任务，也是实际生产生活中经常遇到的需求。ODQA的任务目标是根据大规模语料（知识库），用自然语言的形式来对用户的问题进行回答，而不是仅仅将相关文本片段罗列出来[1][2]。如图一所示[1]，ODQA常见的技术路线包含两个主要模块：检索器（Retriever）和阅读器（Reader）。其中，Retriever模块的作用是根据用户的query在大规模语料中检索到相关联的候选片段，这些片段后面会被喂给Reader输出回答。目前，常用的Retriever有稀疏表示检索（比如，TF-IDF[6]和BM25[3]），以及密集向量检索（比如，DPR[4]和RocketQAv2 [5]）。Reader模块的作用是根据检索出来的相关背景材料，进行理解、总结、提炼、推理等，并给出最终输出人性化（自然语言形式）的回答。常见的Reader采用transformer架构的模型，一般有两种Reader，一种是抽取式（比如，BERT[7]、 RoBERTa[8]等），另一种是文本到文本的生成式Reader（比如，T5[9]、BART[10]、GPT[11]等）。

OpenDomainQA.png

图一、开放域问答框架图

2022年底，OpenAI发布对话大语言模型（Large Language Model, LLM）产品ChatGPT[13]因其“善解人意”和“博闻强识”的特点而走红，在全世界掀起了一场风暴。“善解人意”意味着LLM可以有很强的问题理解能力（query understanding），可以很好地理解用户的问题或指令；“博闻强识”展示了LLM对世界知识的理解能力，可以很好地理解用户给的背景知识，并根据用户问题进行回答。这些特点让大众认识到LLM在ODQA场景的巨大潜力。

不幸的是，强如ChatGPT这样的LLM还是有一些局限性。Chatgpt有时候会给用户错误的回答会误导用户，并且Chatpgt也无法给出它的回答的“信心”[14]。另一方面，即使ChatGPT这类LLM参数量很大，也无法记住海量的世界知识[15]。LLM的预训练知识常常是某一时间之前的，不能很好地“紧跟时代”，会存在知识时效性问题[16]。

检索增强生成（Retrieval-Augmented Generation，RAG）[16]利用检索非参数化的知识来提升知识密集型生成任务的性能，为解决大模型“幻觉”，知识的“时效性”，私域数据等问题提供了很好的方向。最基础的RAG框架如图一所示，其中一个非常基础，也是对效果影响很大的模块就是它的检索模块，获得一个“善解人意”的高效检索器成为大家研究的一个重要方向。

二阶段检索（Two-stage Retriever）
在RAG流程中，检索模块对最终问答正确率和用户体验非常重要。大家认同的一个 检索评判标准 是：1、尽可能召回用户问题所需的相关文本片段，2、越相关的、对回答问题越有帮助的片段应该在检索结果越靠前的位置[17]。

二阶段检索包含检索和精排两个阶段（如图二所示[12]），因其对检索效果和检索速度的很好平衡，成为现在大家在搭建RAG算法流程中的常用选择。检索阶段常常会基于向量检索库的密集向量检索，对用户问题和知识库语料进行语义向量提取，然后搜索和用户问题语义相近的若干片段。提取语义向量的模型一般采用dual-encoder的架构，可以预先（offline）对庞大的知识库语料进行语义向量题去。所以模型只需要实时题去用户问题的语义向量，然后利用向量数据库的向量搜索就可以达成目标。这个过程中（知识库语料）语义向量提取是一个“静态”的过程，模型在提取用户问题和知识库语料的语义向量时，没有信息交互。该方式的好处是效率可以非常高，但这也限制了该阶段的语义检索效果。精排阶段为了解决信息交互的问题，采用cross-encoder架构，cross attention可以使得用户问题和知识库语料有信息交互，可以提取到更加准确的语义关系。该方式的缺点是，需要对用户问题和知识库语料进行实时（online）语义关系提取，效率比较低，无法对大量的知识库语料进行处理。所以检索阶段可以尽量召回用户问题所需的相关文本片段，精排阶段可以将正确相关片段尽可能排在靠前位置。综合检索和精排的优点，二阶段检索可以很好的权衡检索效果和效率，在实际生产中具有巨大潜力。

TwoStageRetriever.jpg

图二、二阶段检索框架

在我们的RAG产品化过程中，二阶段检索也有具体的体现。当知识库语料增大的过程中，里面会充斥很多重复、干扰的信息，密集向量检索由于其能力有限，检索到的相关片段整体质量变差，导致LLM回答效果变差（如图三中，绿色曲线）。当我们采用二阶段检索方式，精排可以对检索到的相关片段进行进一步重排和过滤，可以显著提升最终检索的质量，可以实现数据越多，问答效果越好（如图三中，紫色曲线）。

two_stage_retrieval_advantage.jpg

图三、二阶段检索（QAnything）优势

BCEmbedding - 二阶段检索算法模型库
实现路线
首先我们分析RAG场景检索的目标是什么，需要检索的相关知识片段有什么特征。用户的问题一般可以分为翻译、总结、信息查询、问答等几类需求，所以检索应该具备将不同语种的翻译文本做关联的能力（跨语种检索能力），具备将长原文和短摘要进行关联的能力，具备将不同说法但相同语义的文本做关联的能力，具备将不同问法的问题但相同意图的问题进行关联的能力，具备将问题和可能的答案文本进行关联的能力。此外，为了给问答大模型尽可能高质量的知识片段，检索应该给出尽可能多的相关片段（EmbeddingModel），并且真正有用的片段应该在更靠前的位置（RerankerModel）。

针对上述目标，我们设计了BCEmbedding（Bilingual and Crosslingual Embedding, BCEmbedding）算法模型库，包含EmbeddingModel和RerankerModel两类开源模型。EmbeddingModel可以只需一个模型实现中英双语，以及中英跨语种的检索能力；RerankerModel可以只需一个模型实现中英日韩，以及中英日韩四个语种跨语种语义精排能力。

为了实现上述目标，我们收集开源数据集（包括，摘要、翻译、语义改写、问答等），来实现模型通用的基础语义表征能力。我们利用网易有道强大的翻译引擎，获得双语和四种语言的平行语料，这是实现双语和跨语种的关键步骤。我们分析现有市面上常见或可能的应用场景，收集了包括：教育、医疗、法律、金融、百科、科研论文、客服(faq)、通用QA等场景的语料，使得模型可以覆盖尽可能多的应用场景。设计一套RAG适配的标签分配，EmbeddingModel抛弃Instruction设定，不需要费尽心思设计每个任务设计的instruction，就能实现问题与相似问题检索，问题与候选答案检索，短摘要与长文本检索。利用多语种xlm-roberta-base作为基础模型，提高多语种能力。设计RerankerModel训练loss，使得模型可以输出有意义的参考分数来进一步过滤低质量候选片段，而不是仅仅输出用于排序的相对分数。

关于为什么抛弃instruction，下面结合我们实际使用给出我们的看法。INSTRUCTOR[18]将instruction引入到语义向量表征中，对各个任务、各个数据集设计不同的instruction，可以使模型产生类似LLM指令跟随的能力。当遇到新场景、新数据集时，利用instruction可以实现zero-shot的语义表征能力。类似prompt的作用，设计instruction可以对不同的任务、不同的数据集进行子空间划分，缓解不同任务不同数据集之间数据分布和模式的冲突，激发出模型在预先定义的子空间的语义表征能力。不过，该方式需要对每个任务每个数据“精心”地设计instruction，人工设计痕迹较重，使用起来不方便通用。而且这种人为划分子空间来训练模型的方式，优点是缓解数据分布和模式冲突，代价是复杂化学习目标，非常考验模型本身的容量（能力），比如INSTRUCTOR[18]在Base模型规模上的增益就比Large模型规模的增益小很多。最近开源的语义向量表征模型（语义嵌入模型）将instruction的使用更加简化，只对不同类任务进行instruction设计，或者只对Retrieval任务和非Retrieval任务进行区分。这种简化的方式更像人工设计硬编码一些任务子空间，缓解不同类任务的训练冲突。但此时的instruction已经失去了INSTRCTOR的zero-shot的能力，沦为硬编码（instrcution稍微变一下，会有明显效果损失）。其实更深一步，instruction也可以看成是标签分配的问题，较优的标签分配原则是：1、尽可能相同的数据分布、没有冲突的模式，分成一类，2、类别定义尽量简单，简化学习目标，3、紧跟业务目标（影响评测指标的计算方式）。

根据上述分析，首先考虑到模型能力和实际模型推理效率，我们选用Base规模的模型，该规模的模型本身能力不是那么强悍。我们的算法模型定位是多语种、跨语种和尽可能多的专业领域覆盖。该定位本身目标难度就比较大了，如果再通过instrcution划分子空间复杂化学习任务，可能并不是一个好的选择。其次，在RAG产品使用过程中，用户的实际问题多种多样，用户问题的意图也是千万变化，算法开发者“绞尽脑汁”地精细instrcution设计对用户来说常常是不易理解的，甚至用户自己都不知道他的问题属于算法开发者预定义的哪种类型问题、是否需要instrcution、以及用哪种instrcution，使用起来难度较大。另一方面，RAG中检索的业务目标是，找出用户问题相关的片段。此时不仅仅要检索该问题的答案相关的片段，也要检索该问题相似问题，因为相似问题的上下文常常含有原问题的答案相关内容，比如客服FAQ场景。所以，我们设计一套RAG适配的标签分配规则，将RAG需要检索的目标设置为正例（这个目标可能是相似问题，可能是对应答案，可能是短摘要对应的原长文，也可能是相关的推理过程）。

通过上述路线，我们实现了：

一个模型可以具备中英双语和中英跨语种，尤其是其跨语种能力；
一个模型可以覆盖常见的RAG落地领域，比如：教育、医疗、法律、金融、科研论文、客服(FAQ)、通用QA等场景。
使用说明
我们开源二阶段检索模型EmbeddingModel(bce-embedding-base_v1)和RerankerModel(bce-reranker-base_v1)，可免费商用。同时我们提供一个配套的模型使用算法库BCEmbedding：

EmbeddingModel和RerankerModel可支持BCEmbedding，transformers，sentence-transformers框架推理模型；
提供LangChain和LlamaIndex的集成接口，可方便集成到现有基于LangChain或LlamaIndex的RAG产品中。
RerankerModel提供rerank方法，可以支持长passages（token数超过512）的精排。
RerankerModel提供compute_score方法，可以提供有意义的query和passage的语义相关分数（0～1），可用于在精排阶段，进一步过滤低质量passage，减少无关信息对LLM问答的干扰。
效果说明
语义表征效果
为了检验我们EmbeddingModel在双语和跨语种的能力，我们基于MTEB和C_MTEB评测框架，结合MTEB和CMTEB的公开集，以及我们发布的检验模型跨语种Retrieval能力的跨语种多领域RAG评测集，对包括BCEmbedding在内的现有开源模型进行评测分析。该评测在双语和跨语种设置下进行，也就是['en', 'zh', 'en-zh', 'zh-en']，总共包含MTEB和CMTEB的"Retrieval"， "STS"， "PairClassification"， "Classification"， "Reranking"和"Clustering" 六大类任务的114个数据集，119个评测指标（某些数据集包含多个语种）。所有模型的评测均采用各自推荐的pooling method，其中"jina-embeddings-v2-base-en", "m3e-base", "m3e-large", "e5-large-v2", "multilingual-e5-base", "multilingual-e5-large"和"gte-large"采用mean pooling method，其余模型采用cls pooling method。所有模型均采用各自建议的instruction设置，其中“e5”和“bge”系列模型都需要instruction，其余模型不需要instruction。

模型名称	向量维度	Pooler	特殊指令	Retrieval (47)	STS (19)	PairClassification (5)	Classification (21)	Reranking (12)	Clustering (15)	平均 (119)
bge-base-en-v1.5	768	cls	需要	37.14	55.06	75.45	59.73	43.00	37.74	47.19
bge-base-zh-v1.5	768	cls	需要	47.63	63.72	77.40	63.38	54.95	32.56	53.62
bge-large-en-v1.5	1024	cls	需要	37.18	54.09	75.00	59.24	42.47	37.32	46.80
bge-large-zh-v1.5	1024	cls	需要	47.58	64.73	79.14	64.19	55.98	33.26	54.23
gte-large	1024	mean	不需要	36.68	55.22	74.29	57.73	42.44	38.51	46.67
gte-large-zh	1024	cls	不需要	41.15	64.62	77.58	62.04	55.62	33.03	51.51
jina-embeddings-v2-base-en	768	mean	不需要	31.58	54.28	74.84	58.42	41.16	34.67	44.29
m3e-base	768	mean	不需要	46.29	63.93	71.84	64.08	52.38	37.84	53.54
m3e-large	1024	mean	不需要	34.85	59.74	67.69	60.07	48.99	31.62	46.78
e5-large-v2	1024	mean	需要	35.98	55.23	75.28	59.53	42.12	36.51	46.52
multilingual-e5-base	768	mean	需要	54.73	65.49	76.97	69.72	55.01	38.44	58.34
multilingual-e5-large	1024	mean	需要	56.76	66.79	78.80	71.61	56.49	43.09	60.50
bce-embedding-base_v1	768	cls	不需要	57.60	65.73	74.96	69.00	57.29	38.95	59.43
表一、各类语义嵌入模型的语义表征评测结果

对表一进行分析有以下结论。从语种支持的角度来看，在中英双语和跨语种设置下，multilingual-e5-base、multilingual-e5-large和bce-embedding-base_v1这类多语种、双语种模型表现更佳。相对来说，其他单语种训练得到的模型并不具备很好的多语种能力。其中，bce-embedding-base_v1相对multilingual-e5系列模型，在跨语种能力上表现更佳突出，详见en-zh和zh-en跨语种评测结果。从模型规模来看，bce-embedding-base_v1在同等体量的模型中表现最佳，比如大部分large版本模型表现更好，比最好的多语种multilingual-e5-large表现稍差。从算法设计的角度来看，bce-embedding-base_v1算法设计更宽松，使用起来更方便。向量维度只有768维，对向量数据库存储压力适中；pooler采用最简单、高效的cls方式；也不需要特殊指令，方便集成和使用。综上所述，bce-embedding-base_v1可以一个模型实现很好的中英双语和跨语种能力，而且设置简单，使用很方便。

同样地，维持了检验我们的RerankerModel（bce-reranker-base_v1）的语义精排能力，我们基于MTEB和CMTEB公开评测集，在双语和跨语种设置下（['en', 'zh', 'en-zh', 'zh-en']），利用MTEB和CMTEB的"Reranking"任务的12个数据集进行评测。由下表二可知，我们的bce-reranker-base_v1表现出更好的语义精排能力。

模型名称	Reranking (12)	平均 (12)
bge-reranker-base	59.04	59.04
bge-reranker-large	60.86	60.86
bce-reranker-base_v1	61.29	61.29
表二、Reranker模型语义精排评测结果

LlamaIndex评测RAG效果
LlamaIndex是一个著名的大模型应用的开源工具，在RAG社区中很受欢迎。最近，LlamaIndex博客对市面上常用的embedding和reranker模型进行RAG流程的评测，吸引广泛关注。为了公平起见，我们复刻LlamaIndex博客评测流程，将bce-embedding-base_v1和bce-reranker-base_v1与其他embedding和reranker模型进行对比分析。在此，我们先明确一些情况，LlamaIndex博客的评测只使用了llama v2这一篇英文论文来进行评测的，所以该评测是在纯英文、限定语种（英文）、限定领域（人工智能）场景下进行的。

Embedding Models	WithoutReranker
[hit_rate/mrr]	CohereRerank
[hit_rate/mrr]	bge-reranker-base
[hit_rate/mrr]	bge-reranker-large
[hit_rate/mrr]	bce-reranker-base_v1
[hit_rate/mrr]
OpenAI-ada-2	88.18/64.95	90.45/75.29	91.36/75.74	91.36/76.72	92.27/78.33
bge-large-en	81.36/59.84	86.36/71.61	87.27/73.93	86.82/75.23	88.18/77.36
bge-base-en-v1.5	81.36/57.43	88.64/73.73	89.55/75.23	88.18/74.89	89.09/76.89
bge-large-en-v1.5	83.18/64.34	92.27/76.45	93.18/78.57	92.73/79.59	94.09/81.74
llm-embedder	75.91/54.50	80.91/67.70	81.82/70.05	81.36/69.86	82.73/71.38
CohereV2-en	74.09/51.30	80.91/68.38	82.73/69.86	82.27/69.33	83.18/72.58
CohereV3-en	81.36/58.88	87.73/72.08	88.18/75.29	88.64/75.28	89.09/76.82
JinaAI-v2-Small-en	80.45/57.85	87.73/73.28	88.64/73.72	88.64/74.39	90.00/76.98
JinaAI-v2-Base-en	85.00/61.55	89.55/73.64	90.00/75.52	89.09/75.75	90.91/78.18
gte-large-en	82.27/60.28	90.00/73.77	90.00/75.94	90.00/76.80	91.36/78.42
e5-large-v2-en	88.64/63.80	90.91/75.63	91.36/76.64	91.82/76.90	92.73/79.32
e5-base-multilingual	87.73/64.21	90.45/75.42	93.18/77.20	91.82/78.39	93.64/80.53
e5-large-multilingual	87.27/64.28	90.00/75.33	90.00/75.94	90.00/76.17	91.36/78.64
bce-embedding-base_v1	91.36/71.20	92.73/77.65	95.00/79.01	95.00/79.95	96.36/82.20
表三、LlamaIndex博客评测复刻，对比

如上表三所示，在没有Reranker模块的设置下，bce-embedding-base_v1显著优于其他常见的开源和闭源英文embedding模型。同样地，在相同reranker模型配置下（竖排对比），bce-embedding-base_v1也都是优于其他开源、闭源embedding模型。在相同的embedding配置下（横排对比），利用reranker模型可以显著提升检索效果，验证前面所述二阶段检索的优势。在此之中，bce-reranker-base_v1比其他常见的开源、闭源reranker模型具备更好的精排能力。综上，bce-embedding-base_v1和bce-reranker-base_v1的组合可以实现最好的效果。

多领域、多语种和跨语种RAG效果
正如上所述的LlamaIndex博客评测有些局限，为了兼容更真实更广的用户使用场景，评测算法模型的 领域泛化性，双语和跨语种能力，我们按照该博客的方法构建了一个多领域（计算机科学，物理学，生物学，经济学，数学，量化金融等领域）的中英双语种和中英跨语种评测数据，CrosslingualMultiDomainsDataset。为了使我们这个数据集质量尽可能高，我们采用OpenAI的 gpt-4-1106-preview用于数据生成。为了方式数据泄漏，评测英文数据选择ArXiv上2023年12月30日最新的各领域英文文章；中文数据选择Semantic Scholar相应领域高质量的尽可能新的中文文章。

rag_eval_multiple_domains_summary.jpg

图四、多领域、多语种和跨语种RAG评测

我们针对市面上最强的常用开源、闭源embedding和reranker模型，进行系统性评测分析（如图四）。横排来看，bce-embedding-base_v1的表现和之前一样，具备很好的效果，语种支持和领域覆盖都很不错。openai-ada-2和最新的bge-m3表现出顽强的性能，具备较好的多语种和跨语种能力，具备较好的领域泛化性。Cohere和e5的多语种embedding模型同样表现出不错的效果。而其他单语种embedding模型表现却不尽如人意（虽然bge-large-zh-v1.5稍好一些）。竖排来看，有reranker模块，检索效果改善显著。其中CohereRerank和bge-reranker-large效果相当，bce-reranker-base_v1具备比前二者显著改善的精排能力。综上，bce-embedding-base_v1和bce-reranker-base_v1的组合可以实现最好的检索效果（93.46/77.02），比其他开源闭源最好组合（OpenAI-ada-2+bge-reranker-large， 88.89/69.64），hit rate提升4.57%，mrr提升7.38%。