import requests
import pandas as pd
import re
import os
import shutil
from pathlib import Path
import time

def test_ollama_connection(model='llama2'):
    """Test if Ollama is running and accessible"""
    print("🔧 Testing Ollama connection...")
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=10)
        if response.status_code == 200:
            models = response.json().get('models', [])
            print(f"✅ Ollama is running! Available models: {[m['name'] for m in models]}")
            return True
        else:
            print(f"❌ Ollama responded with status code: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to Ollama. Make sure it's running on localhost:11434")
        return False
    except Exception as e:
        print(f"❌ Error testing connection: {e}")
        return False

def ollama_classify_score(essay, model='llama2'):
    """WORKING classification function from v3.0"""
    prompt = f"""You are an expert essay classifier. Read this essay carefully and determine if it is SPECIFICALLY about Independence Day.

INDEPENDENCE DAY topics include:
- August 15th celebrations
- Indian freedom struggle 
- Freedom fighters (Gandhi, Nehru, etc.)
- Flag hoisting ceremonies
- Patriotic themes related to India's independence

NON-INDEPENDENCE DAY topics include:
- Sports, technology, education, environment
- Career goals, social media, books
- General topics not related to Indian independence

Essay to classify:
{essay[:800]}

IMPORTANT: Respond in EXACTLY this format:
TOPIC: [Independence Day] OR [Other Topic]
CLASSIFICATION: [YES] OR [NO]
SCORE: [1.0 to 5.0]

Your response:"""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model, 
                "prompt": prompt, 
                "stream": False,
                "options": {"temperature": 0.1, "top_p": 0.9}
            },
            timeout=90
        )
        
        if response.status_code != 200:
            return "Error", None, f"HTTP {response.status_code}"
            
        output = response.json().get("response", "").strip()
        
        # Parse classification
        classification_match = re.search(r'CLASSIFICATION:\s*(YES|NO)', output, re.IGNORECASE)
        classification = "Yes" if classification_match and classification_match.group(1).upper() == "YES" else "No"
        
        if classification == "No":  # Additional fallback logic from v3.0
            essay_lower = essay.lower()
            independence_keywords = [
                'independence day', 'august 15', '15th august', 'freedom struggle', 
                'british rule', 'gandhi', 'nehru', 'freedom fighter', 'patriotic',
                'tiranga', 'tricolor', 'national flag', 'red fort', 'partition'
            ]
            other_keywords = [
                'social media', 'facebook', 'instagram', 'environmental protection', 
                'climate change', 'career goals', 'software engineer', 'online education',
                'covid-19', 'sports importance', 'basketball', 'cricket', 'wings of fire'
            ]
            
            independence_score = sum(1 for keyword in independence_keywords if keyword in essay_lower)
            other_score = sum(1 for keyword in other_keywords if keyword in essay_lower)
            
            if independence_score > other_score and independence_score >= 2:
                classification = "Yes"
        
        # Parse score
        score_match = re.search(r'SCORE:\s*([1-5](?:\.[0-9])?)', output, re.IGNORECASE)
        score = float(score_match.group(1)) if score_match else 3.0
        
        return classification, score, output
        
    except Exception as e:
        return "Error", None, str(e)

def quick_essay_analysis(essay, filename, model='llama2'):
    """Simplified, faster analysis that won't timeout"""
    # Shorter essay content for faster processing
    essay_preview = essay[:1000] if len(essay) > 1000 else essay
    
    prompt = f"""Rate this Independence Day essay quickly on a 1-10 scale:

Essay: {filename}
Content: {essay_preview}

Rate these 5 aspects (1-10):
Relevance: How relevant to Independence Day?
Content: How good is the content?
Writing: How well written?
Original: How original/unique?
Impact: How inspiring/emotional?

Answer ONLY in this format:
Relevance: 8
Content: 7
Writing: 9
Original: 6
Impact: 8
Strengths: [Brief list]
Topics: [Independence Day topics covered]"""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model, 
                "prompt": prompt, 
                "stream": False,
                "options": {"temperature": 0.1}
            },
            timeout=45  # Shorter timeout
        )
        
        if response.status_code != 200:
            return None
            
        output = response.json().get("response", "").strip()
        print(f"    📊 Analysis response: {output[:150]}...")
        
        # Parse ratings
        analysis = {}
        patterns = {
            'relevance': r'Relevance:\s*(\d+)',
            'content': r'Content:\s*(\d+)',
            'writing': r'Writing:\s*(\d+)',
            'original': r'Original:\s*(\d+)',
            'impact': r'Impact:\s*(\d+)'
        }
        
        scores = []
        for key, pattern in patterns.items():
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                score = int(match.group(1))
                analysis[key] = min(max(score, 1), 10)  # Ensure 1-10 range
                scores.append(analysis[key])
            else:
                analysis[key] = 6  # Default
                scores.append(6)
        
        # Calculate overall score
        analysis['overall_score'] = sum(scores) / len(scores)
        
        # Extract text sections
        strengths_match = re.search(r'Strengths:\s*(.+?)(?=Topics:|$)', output, re.IGNORECASE | re.DOTALL)
        topics_match = re.search(r'Topics:\s*(.+?)$', output, re.IGNORECASE | re.DOTALL)
        
        analysis['strengths'] = strengths_match.group(1).strip() if strengths_match else "Good Independence Day essay"
        analysis['topics'] = topics_match.group(1).strip() if topics_match else "Independence Day themes"
        
        # Assign grade
        score = analysis['overall_score']
        if score >= 9:
            grade = "A+"
        elif score >= 8:
            grade = "A"
        elif score >= 7:
            grade = "B+"
        elif score >= 6:
            grade = "B"
        elif score >= 5:
            grade = "C+"
        else:
            grade = "C"
        
        analysis['grade'] = grade
        analysis['raw_output'] = output
        
        return analysis
        
    except Exception as e:
        print(f"    ❌ Quick analysis error: {e}")
        return None

def simple_comparative_ranking(essays_data, model='llama2'):
    """Simpler comparative ranking that won't timeout"""
    
    # Create a concise summary
    summary_lines = []
    for i, data in enumerate(essays_data):
        analysis = data.get('analysis', {})
        summary_lines.append(
            f"{i+1}. {data['filename']} - Score: {analysis.get('overall_score', 5.0):.1f}/10 "
            f"- Strengths: {analysis.get('strengths', 'N/A')[:50]}..."
        )
    
    essays_summary = "\n".join(summary_lines)
    
    prompt = f"""Rank these {len(essays_data)} Independence Day essays from best to worst:

{essays_summary}

Give final ranking in this format:
1st: [filename] - [9.0-10.0] - Why it's best
2nd: [filename] - [8.0-8.9] - Why it's second  
3rd: [filename] - [7.0-7.9] - Why it's third
[continue for all essays]

Keep explanations brief (1 sentence each)."""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model, 
                "prompt": prompt, 
                "stream": False,
                "options": {"temperature": 0.2}
            },
            timeout=60  # Shorter timeout
        )
        
        if response.status_code != 200:
            return "Ranking analysis failed - timeout or error"
            
        output = response.json().get("response", "").strip()
        return output
        
    except Exception as e:
        return f"Ranking error: {str(e)}"

def read_file_content(file_path):
    """Read content from various file formats"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
            print(f"  📄 File read successfully: {len(content)} characters")
            return content
    except Exception as e:
        print(f"  ❌ Error reading file: {str(e)}")
        return f"Error reading file: {str(e)}"

def process_essay_folder_with_quick_analysis(input_folder_path):
    """Enhanced processing with faster, more reliable analysis"""
    input_folder = Path(input_folder_path)
    
    if not input_folder.exists():
        print(f"❌ Error: Folder '{input_folder_path}' does not exist!")
        return []
    
    if not test_ollama_connection():
        print("\n💡 Make sure Ollama is running: ollama run llama2")
        return []
    
    # Create folders
    wrong_files_folder = input_folder / "wrong_files"
    analysis_folder = input_folder / "essay_analysis"
    wrong_files_folder.mkdir(exist_ok=True)
    analysis_folder.mkdir(exist_ok=True)
    
    # Get all text files
    text_extensions = ['.txt', '.md', '.rtf']
    essay_files = []
    for ext in text_extensions:
        essay_files.extend(list(input_folder.glob(f'*{ext}')))
    
    if not essay_files:
        print(f"❌ No essay files found in '{input_folder_path}'")
        return []
    
    print(f"\n🎯 PHASE 1: Classification of {len(essay_files)} essays")
    print("="*80)
    
    # Phase 1: Basic classification
    independence_day_essays = []
    wrong_topic_essays = []
    
    for i, file_path in enumerate(essay_files, 1):
        print(f"\n📁 Processing {i}/{len(essay_files)}: {file_path.name}")
        print("-" * 50)
        
        content = read_file_content(file_path)
        if content.startswith("Error reading file"):
            continue
        
        print(f"  📝 Preview: {content[:80]}...")
        print(f"  📤 Sending to LLM...")
        
        classification, score, raw_response = ollama_classify_score(content)
        print(f"  📥 Response: {raw_response[:100]}...")
        print(f"  📊 Result: {classification}, Score: {score}")
        
        if classification == "Error":
            print(f"  ❌ Classification error: {raw_response}")
        elif classification.lower() == 'yes':
            independence_day_essays.append({
                'filename': file_path.name,
                'filepath': str(file_path),
                'content': content,
                'basic_score': score
            })
            print(f"  ✅ Independence Day essay")
        elif classification.lower() == 'no':
            wrong_topic_essays.append({'filename': file_path.name})
            print(f"  ❌ Moving to wrong_files")
            
            try:
                destination = wrong_files_folder / file_path.name
                shutil.move(str(file_path), str(destination))
                print(f"    📁 Moved to: {destination}")
            except Exception as e:
                print(f"    ⚠️ Move error: {e}")
        
        time.sleep(1)  # Brief pause
    
    if not independence_day_essays:
        print("❌ No Independence Day essays found!")
        return []
    
    print(f"\n🎯 PHASE 2: Quick Analysis of {len(independence_day_essays)} essays")
    print("="*80)
    
    # Phase 2: Quick analysis
    successful_analyses = []
    
    for i, essay_data in enumerate(independence_day_essays, 1):
        print(f"\n📊 Analyzing {i}/{len(independence_day_essays)}: {essay_data['filename']}")
        
        analysis = quick_essay_analysis(essay_data['content'], essay_data['filename'])
        
        if analysis:
            essay_data['analysis'] = analysis
            successful_analyses.append(essay_data)
            print(f"  ✅ Success - Overall: {analysis['overall_score']:.1f}/10 ({analysis['grade']})")
        else:
            print(f"  ⚠️ Analysis failed - using defaults")
            # Provide basic default analysis
            essay_data['analysis'] = {
                'overall_score': 6.0,
                'relevance': 6, 'content': 6, 'writing': 6, 'original': 6, 'impact': 6,
                'grade': 'B', 'strengths': 'Independence Day themed essay',
                'topics': 'Independence Day celebrations'
            }
            successful_analyses.append(essay_data)
        
        time.sleep(1)
    
    print(f"\n🎯 PHASE 3: Final Ranking")
    print("="*80)
    
    # Phase 3: Simple ranking
    print(f"🔬 Generating final ranking...")
    final_ranking = simple_comparative_ranking(successful_analyses)
    
    print("\n" + "="*80)
    print("🎉 COMPETITION ANALYSIS COMPLETE!")
    print("="*80)
    
    # Generate results
    if successful_analyses:
        # Sort by score
        sorted_essays = sorted(successful_analyses, 
                             key=lambda x: x['analysis']['overall_score'], 
                             reverse=True)
        
        # Create report
        report = "# INDEPENDENCE DAY ESSAY COMPETITION RESULTS\n\n"
        report += f"## OVERVIEW\n"
        report += f"- Total submissions: {len(essay_files)}\n"
        report += f"- Valid Independence Day essays: {len(successful_analyses)}\n"
        report += f"- Disqualified (other topics): {len(wrong_topic_essays)}\n\n"
        
        report += "## ESSAY SCORES\n\n"
        
        for i, essay in enumerate(sorted_essays, 1):
            analysis = essay['analysis']
            report += f"### {i}. {essay['filename']} - {analysis['overall_score']:.1f}/10 ({analysis['grade']})\n\n"
            report += f"**Detailed Scores:**\n"
            report += f"- Relevance to Independence Day: {analysis['relevance']}/10\n"
            report += f"- Content Quality: {analysis['content']}/10\n"
            report += f"- Writing Quality: {analysis['writing']}/10\n"
            report += f"- Originality: {analysis['original']}/10\n"
            report += f"- Emotional Impact: {analysis['impact']}/10\n\n"
            report += f"**Key Strengths:** {analysis['strengths']}\n\n"
            report += f"**Independence Day Topics:** {analysis['topics']}\n\n"
            report += "---\n\n"
        
        if final_ranking:
            report += "## JUDGE'S FINAL RANKING\n\n"
            report += final_ranking + "\n\n"
        
        # Save files
        report_path = analysis_folder / "competition_results.md"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        
        # CSV data
        csv_data = []
        for essay in successful_analyses:
            analysis = essay['analysis']
            csv_data.append({
                'filename': essay['filename'],
                'overall_score': analysis['overall_score'],
                'grade': analysis['grade'],
                'relevance': analysis['relevance'],
                'content_quality': analysis['content'],
                'writing_quality': analysis['writing'],
                'originality': analysis['original'],
                'emotional_impact': analysis['impact'],
                'strengths': analysis['strengths'],
                'topics_covered': analysis['topics'],
                'word_count': len(essay['content'].split())
            })
        
        df = pd.DataFrame(csv_data)
        df = df.sort_values('overall_score', ascending=False)
        df.to_csv(analysis_folder / "essay_scores.csv", index=False)
        
        # Print results summary
        print(f"💾 Results saved to: {analysis_folder}/")
        print(f"📄 Full Report: competition_results.md")
        print(f"📊 Score Data: essay_scores.csv")
        
        print(f"\n🏆 FINAL COMPETITION RESULTS:")
        print(f"Valid Entries: {len(successful_analyses)} essays")
        print(f"Average Score: {df['overall_score'].mean():.2f}/10")
        print(f"Top Score: {df['overall_score'].max():.2f}/10")
        print(f"Score Range: {df['overall_score'].min():.2f} - {df['overall_score'].max():.2f}")
        
        print(f"\n🥇 TOP 5 ESSAYS:")
        for i in range(min(5, len(df))):
            row = df.iloc[i]
            print(f"  {i+1}. {row['filename']}")
            print(f"     Score: {row['overall_score']:.1f}/10 ({row['grade']}) - {row['strengths'][:60]}...")
        
        # Show ranking preview
        if final_ranking and ("1st:" in final_ranking or "1." in final_ranking):
            print(f"\n🎖️ JUDGE'S RANKING PREVIEW:")
            lines = final_ranking.split('\n')[:5]
            for line in lines:
                if line.strip() and any(x in line for x in ['1st', '2nd', '3rd', '1.', '2.', '3.']):
                    print(f"  {line.strip()}")
    
    return successful_analyses  # Return for multi-zone use

# MULTI-ZONE FUNCTIONS
def process_single_zone_for_multi(zone_folder_path, zone_name, model='llama2'):
    """
    Wrapper around existing process_essay_folder_with_quick_analysis 
    but returns top 3 essays for multi-zone comparison
    """
    print(f"\n🎯 Processing Zone: {zone_name}")
    print("=" * 60)
    
    # Use existing function
    successful_analyses = process_essay_folder_with_quick_analysis(zone_folder_path)
    
    if not successful_analyses:
        print(f"⚠️ No valid essays found for {zone_name}")
        return []
    
    # Sort by score and get top 3
    sorted_essays = sorted(successful_analyses, 
                         key=lambda x: x['analysis']['overall_score'], 
                         reverse=True)
    
    top_3_data = []
    for i in range(min(3, len(sorted_essays))):
        essay = sorted_essays[i]
        top_3_data.append({
            'filename': essay['filename'],
            'zone': zone_name,
            'content': essay['content'],
            'overall_score': essay['analysis']['overall_score'],
            'grade': essay['analysis']['grade'],
            'strengths': essay['analysis']['strengths'],
            'analysis': essay['analysis'],
            'zone_rank': i + 1
        })
    
    print(f"✅ {zone_name}: Top {len(top_3_data)} essays selected for grand competition")
    return top_3_data

def compare_zones_top_essays(all_zone_essays, model='llama2'):
    """Compare top essays from all zones"""
    
    # Create summary for LLM
    combined_summary = ""
    essay_count = 0
    
    for zone_essays in all_zone_essays:
        if zone_essays:  # If zone has essays
            zone_name = zone_essays[0]['zone']
            combined_summary += f"\n=== {zone_name} Top Essays ===\n"
            
            for essay in zone_essays:
                essay_count += 1
                combined_summary += f"\nEssay {essay_count}: {essay['filename']} (from {zone_name})\n"
                combined_summary += f"Zone Rank: #{essay['zone_rank']}, Zone Score: {essay['overall_score']:.1f}/10\n"
                combined_summary += f"Strengths: {essay['strengths']}\n"
                combined_summary += f"Content Preview: {essay['content'][:400]}...\n"
    
    prompt = f"""You are the GRAND JUDGE for a multi-zone Independence Day essay competition. 

You must rank ALL the top essays from different zones against each other to find the ultimate winner.

{combined_summary}

Your task:
1. Rank ALL essays from BEST to WORST across all zones
2. Give each essay a final competition score (1-10)
3. Explain why the winner deserves the top position
4. Compare performance between zones
5. Identify which zone produced the highest quality essays

Respond in this EXACT format:

🏆 GRAND CHAMPIONSHIP RANKING 🏆

1st Place: [Filename] from [Zone] - Final Score: [9.0-10.0]
   Champion Qualities: [Why this essay wins the entire competition]
   
2nd Place: [Filename] from [Zone] - Final Score: [8.5-9.0]
   Excellence: [What makes this essay exceptional]
   
3rd Place: [Filename] from [Zone] - Final Score: [8.0-8.5]
   Strengths: [Why this essay deserves bronze]

[Continue for all essays...]

🏅 ZONE PERFORMANCE ANALYSIS 🏅
Zone A Performance: [Overall assessment]
Zone B Performance: [Overall assessment]
[Continue for all zones...]

🎖️ COMPETITION INSIGHTS 🎖️
Best Performing Zone: [Zone name and why]
Overall Competition Quality: [Assessment of all essays]
Key Differentiators: [What separated top essays from others]

GRAND CHAMPION CITATION:
[Special recognition for the ultimate winner with detailed reasoning]
"""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model, 
                "prompt": prompt, 
                "stream": False,
                "options": {"temperature": 0.3}
            },
            timeout=180
        )
        
        if response.status_code == 200:
            return response.json().get("response", "")
        else:
            return f"Error: HTTP {response.status_code}"
            
    except Exception as e:
        return f"Error in grand comparison: {str(e)}"

def multi_zone_competition():
    """Main function for multi-zone competition"""
    print("🏆 MULTI-ZONE INDEPENDENCE DAY ESSAY COMPETITION 🏆")
    print("=" * 70)
    
    # Get number of zones
    try:
        num_zones = int(input("Enter number of zones/folders to compare: "))
        if num_zones < 2:
            print("❌ Need at least 2 zones for comparison!")
            return
    except ValueError:
        print("❌ Invalid number!")
        return
    
    all_zone_essays = []
    zone_names = []
    
    # Process each zone
    for i in range(num_zones):
        print(f"\n📂 Zone {i+1} Setup:")
        zone_folder = input(f"Enter path for Zone {i+1} folder: ").strip().strip('"').strip("'")
        zone_name = input(f"Enter name for Zone {i+1} (e.g., 'School A', 'District B'): ").strip()
        
        if not Path(zone_folder).exists():
            print(f"❌ Folder not found: {zone_folder}")
            continue
        
        zone_names.append(zone_name)
        
        # Process this zone
        top_essays = process_single_zone_for_multi(zone_folder, zone_name)
        all_zone_essays.append(top_essays)
        
        if top_essays:
            print(f"✅ {zone_name}: Found {len(top_essays)} top essays")
            for j, essay in enumerate(top_essays, 1):
                print(f"   {j}. {essay['filename']} - {essay['overall_score']:.1f}/10")
        else:
            print(f"⚠️ {zone_name}: No valid essays found")
    
    # Filter out empty zones
    valid_zones = [(name, essays) for name, essays in zip(zone_names, all_zone_essays) if essays]
    
    if len(valid_zones) < 2:
        print("❌ Need at least 2 zones with valid essays for comparison!")
        return
    
    print(f"\n🎯 GRAND COMPARISON PHASE")
    print("=" * 50)
    
    total_essays = sum(len(essays) for _, essays in valid_zones)
    print(f"Comparing {total_essays} top essays from {len(valid_zones)} zones...")
    
    # Perform grand comparison
    grand_result = compare_zones_top_essays([essays for _, essays in valid_zones])
    
    # Display results
    print("\n" + "=" * 80)
    print("🏆 GRAND CHAMPIONSHIP RESULTS 🏆")
    print("=" * 80)
    print(grand_result)
    
    # Save combined results
    results_folder = Path("multi_zone_championship_results")
    results_folder.mkdir(exist_ok=True)
    
    with open(results_folder / "grand_championship_report.md", 'w', encoding='utf-8') as f:
        f.write("# MULTI-ZONE INDEPENDENCE DAY ESSAY CHAMPIONSHIP\n\n")
        f.write(f"**Competition Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**Participating Zones:** {len(valid_zones)}\n")
        f.write(f"**Total Essays Compared:** {total_essays}\n\n")
        f.write("## GRAND CHAMPIONSHIP RESULTS\n\n")
        f.write(grand_result)
    
    print(f"\n💾 Grand championship results saved to: {results_folder}/")
    print("📄 Report: grand_championship_report.md")

def main():
    print("🎯 Independence Day Essay Competition System v5.0")
    print("=" * 60)
    
    print("Choose mode:")
    print("1. Single Zone Analysis (analyze one folder)")
    print("2. Multi-Zone Championship (compare multiple zones)")
    
    try:
        choice = input("Enter choice (1 or 2): ").strip()
        
        if choice == "1":
            # Use existing single-zone function
            folder_path = input("Enter essay folder path: ").strip().strip('"').strip("'")
            print(f"📂 Processing: {folder_path}")
            process_essay_folder_with_quick_analysis(folder_path)
            
        elif choice == "2":
            # Use new multi-zone function
            multi_zone_competition()
            
        else:
            print("❌ Invalid choice! Please enter 1 or 2.")
            
    except KeyboardInterrupt:
        print("\n\n👋 Competition analysis cancelled by user.")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()
