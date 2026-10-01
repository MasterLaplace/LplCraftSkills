The core of Laplace in one place: [LplKernel](https://github.com/MasterLaplace/LplKernel), [LplPlugin](https://github.com/MasterLaplace/LplPlugin), [LplKnowledge](https://github.com/MasterLaplace/LplKnowledge), [LplCraftSkills](https://github.com/MasterLaplace/LplCraftSkills) and [LplAssistant](https://github.com/Christian-guajardo/LplAssistant).

## Which view answers which question

| Question | View |
|---|---|
| What can I take next? | **Next** |
| What waits for a review? | **To review** |
| Where is forgeron? | **Forgeron** |
| Where is the project going? | **Roadmap** |
| What waits for the maintainer? | **Waiting on me** |
| What has not moved for 14 days? | **Stale** |
| What shipped, version by version? | **Shipped** |
| What can a newcomer take? | **Newcomers** |

## What each status means

| Status | Meaning | Set by |
|---|---|---|
| *No status* | Just arrived, not triaged yet: this is the inbox. | nobody |
| Ready | Triaged: anyone can take it. | the maintainer |
| In progress | Someone works on it. | a pull request linked to the issue |
| To review | The pull request waits for a review. | the pull request entering the project |
| Changes requested | The review asked for changes. | the review |
| To re-review | The author answered the review. | **the author, by hand** |
| Approved | The review approved the pull request. | the review |
| Done | Closed or merged. | closing or merging |

**Priority** says what comes first. **Forgeron** shows where the [forgeron](https://github.com/MasterLaplace/LplCraftSkills/tree/main/forgeron) pilot is on the issues it works on.

## How items get here

New issues and pull requests of the MasterLaplace repositories are added automatically, and a sub-issue follows its parent. Items of LplAssistant are added by forgeron or by hand.

## The roadmap

A goal is an issue of [MasterLaplace/.github](https://github.com/MasterLaplace/.github) with a **Start date** and a **Target date**. Its sub-issues live in the repositories that do the work. Milestones are the versions of each repository, and show as markers on the roadmap.

## Contributing

Start with the **Newcomers** view, then read [CONTRIBUTING](https://github.com/MasterLaplace/.github/blob/main/.github/CONTRIBUTING.md) and the [code of conduct](https://github.com/MasterLaplace/.github/blob/main/.github/CODE_OF_CONDUCT.md).
