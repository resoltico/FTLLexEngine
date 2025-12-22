# Patent Considerations

This document provides detailed information about patent considerations for FTLLexEngine users and contributors.

## Summary for Users

**FTLLexEngine is licensed under the MIT License, which does not include explicit patent grant language.**

If patent protection is a concern for your use case, please consult with legal counsel to assess your specific situation.

## Background: Specification vs. Implementation

FTLLexEngine implements the FTL Syntax Specification, which has different licensing from this implementation:

| Component | License | Patent Grant |
|-----------|---------|--------------|
| FTL Syntax Specification | Apache License 2.0 | Yes (explicit) |
| FTLLexEngine (this implementation) | MIT License | No (implicit only) |

## Apache 2.0 Specification Patent Grant

The FTL Syntax Specification is licensed under Apache License 2.0, which includes Section 3 (Grant of Patent License):

> Subject to the terms and conditions of this License, each Contributor hereby grants to You a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable (except as stated in this section) patent license to make, have made, use, offer to sell, sell, import, and otherwise transfer the Work...

**This patent grant applies to the specification itself**, covering contributions made by specification authors (primarily Mozilla Foundation and contributors to the Fluent project).

## MIT License and Patents

The MIT License grants broad permissions ("to deal in the Software without restriction") but does not explicitly mention patents. Legal interpretation varies:

### Implicit Patent License Theory

Some legal scholars argue the MIT License includes an **implied patent license** through phrases like:
- "without restriction"
- "without limitation"
- "use, copy, modify, merge, publish, distribute, sublicense"

However, this is **not universally accepted** and may not hold in all jurisdictions.

### No Explicit Grant

Unlike Apache 2.0, the MIT License:
- Does NOT explicitly grant patent rights
- Does NOT include patent retaliation clauses
- Does NOT define what "use" means in patent terms

## What This Means for FTLLexEngine

### For Users

**FTLLexEngine makes no patent claims and knowingly infringes no patents.**

This is an **independent, clean-room implementation** of a publicly available specification:

1. **Specification Patents**: The Apache 2.0 patent grant from specification authors may provide coverage for implementing the specification
2. **Implementation Patents**: This implementation is original work with no known patent issues
3. **No Patent Claims**: The copyright holder (Ervins Strauhmanis) makes no patent claims on this implementation

### Comparison with Other Licenses

| License | Explicit Patent Grant | Patent Retaliation | Widely Used |
|---------|----------------------|-------------------|-------------|
| Apache 2.0 | Yes | Yes | Yes |
| MIT | No | No | Yes |
| BSD-2-Clause | No | No | Yes |
| BSD-3-Clause | No | No | Yes |
| GPL v3 | Yes | Yes | Yes |

**Note**: Many successful open-source projects use MIT/BSD licenses without explicit patent grants, including:
- jQuery (MIT)
- Rails (MIT)
- Node.js (MIT)
- React (MIT, changed from BSD+Patents in 2017)
- Angular (MIT)

## For Contributors

By contributing to FTLLexEngine, you:

1. **Grant MIT License permissions** for your contributions (copyright license)
2. **Do NOT explicitly grant patent rights** (MIT License has no patent clause)
3. **Should not contribute code** that you know infringes patents you hold
4. **Should disclose** if you have patent concerns about your contribution

### Contribution Guidelines

**Before contributing:**

- Ensure your contribution is your original work
- Do not contribute code you know infringes patents (yours or others)
- If you hold patents related to your contribution, consider whether you're comfortable with the MIT License's implicit permissions
- Disclose any known patent issues in your pull request

**By submitting a pull request, you represent that:**

- You have the right to submit the code
- Your contribution does not knowingly infringe patents
- You grant MIT License permissions for your contribution

## Why Not Use Apache 2.0?

You might ask: "Why not license FTLLexEngine under Apache 2.0 to get explicit patent grants?"

**Reasons for MIT License:**

1. **Simplicity**: MIT is one of the shortest, easiest-to-understand licenses
2. **Compatibility**: MIT is compatible with virtually all other licenses
3. **Ecosystem**: Python ecosystem heavily uses MIT (matches community norms)
4. **Low Barrier**: MIT imposes minimal requirements on users
5. **No Patent Claims**: This implementation makes no patent claims to grant

## Risk Assessment

### Realistic Patent Risk

For most users, patent risk is **extremely low**:

1. **Specification Coverage**: Apache 2.0 patent grant from specification authors likely covers implementation
2. **Published Specification**: Implementing published specs is generally considered low-risk
3. **No Known Issues**: No known patent claims against Fluent implementations
4. **Defensive Publication**: Public specifications serve as prior art

### Higher-Risk Scenarios

Consult legal counsel if:

- You work in highly patent-litigious industries (e.g., telecommunications)
- You have specific patent concerns about localization technology
- Your organization has strict patent policy requirements
- You're considering patenting derivative works

## Alternative Implementations

If explicit patent grants are required for your use case, consider:

| Implementation | License | Patent Grant |
|----------------|---------|--------------|
| FTLLexEngine | MIT | No |
| fluent.runtime (Mozilla) | Apache 2.0 | Yes |
| fluent-compiler | Apache 2.0 | Yes |

All three implement the same FTL Specification v1.0 and are functionally compatible.

## Patent Non-Assertion

The copyright holder (Ervins Strauhmanis) states:

**"This implementation makes no patent claims and is not aware of any patents that this implementation infringes. If any patents are held by the copyright holder that relate to this implementation, permission is granted under the MIT License to use this implementation without patent liability."**

This is a non-binding statement of intent, not a legal patent grant.

## Questions and Concerns

### I found a patent issue

Please report immediately:
1. Open a GitHub issue (mark as SECURITY if sensitive)
2. Email: [your-contact-email] (TODO: Add contact email)
3. Include: patent number, jurisdiction, specific claims

### I need explicit patent protection

**Options:**
1. Use Apache 2.0-licensed alternatives (fluent.runtime, fluent-compiler)
2. Obtain legal opinion that MIT License provides sufficient coverage
3. Negotiate separate patent license (contact copyright holder)

### I want to contribute but hold patents

**Please:**
1. Disclose in your pull request
2. Confirm you're comfortable with MIT License implicit permissions
3. Consider whether you want to make a patent non-assertion statement

### Can FTLLexEngine change to Apache 2.0?

Relicensing would require:
1. Agreement from all past contributors
2. Architectural decision to prioritize patent grants over MIT simplicity
3. Community discussion

This is possible but not currently planned.

## Legal Disclaimer

**This document is for informational purposes only and does not constitute legal advice.**

Patent law is complex and varies by jurisdiction. This document represents the copyright holder's understanding and intent but may not be legally binding.

**For patent-related concerns, consult qualified legal counsel in your jurisdiction.**

## Further Reading

### MIT License and Patents

- [MIT License on OSI](https://opensource.org/licenses/MIT)
- [MIT License Compatibility](https://en.wikipedia.org/wiki/MIT_License)

### Apache 2.0 Patent Provisions

- [Apache 2.0 License Full Text](https://www.apache.org/licenses/LICENSE-2.0)
- [Understanding Apache 2.0 Patent Grant](https://opensource.com/article/18/2/apache-2-patent-license)

### General Patent Information

- [USPTO: Explore Intellectual Property](https://www.uspto.gov/kids/explore-intellectual-property)
- [Open Source Licenses and Patents](https://www.fossa.com/blog/open-source-licenses-101-apache-license-2-0/)

---

**Last Updated**: 2025-11-25

**Contact**: See [NOTICE](NOTICE) file for copyright holder information.
