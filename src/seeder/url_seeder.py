"""
Enterprise-Scale URL Seeder for 2M+ URL Discovery
Generates master_seed.xml and comprehensive seeds database
"""

import asyncio
import json
import logging
import time
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict
import uuid
import os
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit, urlunsplit

from crawl4ai import AsyncUrlSeeder, SeedingConfig
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer

from src.config.settings import settings
from src.seeder.sources import ALL_ENTERPRISE_SOURCES, get_top_sources, calculate_total_estimated_urls

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EnterpriseURLSeeder:
    """
    Enterprise-scale URL seeder for 2M+ URL discovery.
    
    Generates:
    - master_seed.xml (XML sitemap for crawling)
    - seeds.json (comprehensive JSON index)
    - Detailed metrics and reporting
    """
    
    def __init__(self):
        """Initialize enterprise seeder."""
        self.correlation_id = str(uuid.uuid4())[:8]
        self.discovered_urls: Set[str] = set()
        self.urls_by_source: Dict[str, List[Dict[str, Any]]] = {}
        self.failed_sources: List[Dict[str, Any]] = []
        self.source_metrics: Dict[str, Dict[str, Any]] = {}
        
        self.metrics = {
            'start_time': time.time(),
            'total_urls': 0,
            'total_urls_estimated': calculate_total_estimated_urls(),
            'sources_succeeded': 0,
            'sources_failed': 0,
        }
        
        logger.info(f"[{self.correlation_id}] ✓ Enterprise URLSeeder initialized")
        logger.info(f"[{self.correlation_id}] Estimated total URLs: {self.metrics['total_urls_estimated']:,}")
    
    def _build_seeding_config(
        self,
        domain: str,
        source_config: Dict[str, Any]
    ) -> SeedingConfig:
        """Build SeedingConfig for source."""
        patterns = source_config.get("patterns", ["*"])
        pattern = patterns[0] if patterns else "*"
        
        return SeedingConfig(
            source=source_config.get("source", "sitemap+cc"),
            pattern=pattern,
            max_urls=source_config.get("max_urls", 50000),
            concurrency=source_config.get("concurrency", 30),
            hits_per_sec=source_config.get("hits_per_sec", 15.0),
            live_check=source_config.get("live_check", False),
            verbose=False,
            filter_nonsense_urls=True,
            extract_head=True,
        )
    
    async def seed_urls(
        self,
        source_domains: Optional[List[str]] = None,
        tier_mode: str = "all",  # "mega" | "top30" | "all"
    ) -> Dict[str, Any]:
        """
        Discover URLs from enterprise sources.
        
        Args:
            source_domains: Specific domains to seed
            tier_mode: "mega" (100K+ only), "top30", or "all"
            
        Returns:
            Dictionary with results and metrics
        """
        # Select sources
        if source_domains:
            sources_to_seed = {d: ALL_ENTERPRISE_SOURCES[d] for d in source_domains if d in ALL_ENTERPRISE_SOURCES}
        elif tier_mode == "mega":
            sources_to_seed = {k: v for k, v in ALL_ENTERPRISE_SOURCES.items() if v.get("urls_estimate", 0) >= 100000}
        elif tier_mode == "top30":
            sources_to_seed = get_top_sources(30)
        else:  # "all"
            sources_to_seed = ALL_ENTERPRISE_SOURCES
        
        logger.info(f"\n{'='*90}")
        logger.info(f"[{self.correlation_id}] [ENTERPRISE URL SEEDING] Starting")
        logger.info(f"{'='*90}")
        logger.info(f"Sources to seed: {len(sources_to_seed)}")
        logger.info(f"Tier mode: {tier_mode}")
        logger.info(f"Estimated URLs: {sum(v.get('urls_estimate', 0) for v in sources_to_seed.values()):,}")
        logger.info(f"{'='*90}\n")
        
        try:
            async with AsyncUrlSeeder() as seeder:
                # Process sources in batches by priority
                sorted_sources = sorted(
                    sources_to_seed.items(),
                    key=lambda x: (x[1].get("priority", 5), -x[1].get("reputation", 0))
                )
                
                for i, (domain, source_config) in enumerate(sorted_sources, 1):
                    await self._seed_domain(
                        seeder,
                        domain,
                        source_config,
                        i,
                        len(sorted_sources)
                    )
            
            # Final metrics
            self.metrics['end_time'] = time.time()
            self.metrics['total_urls'] = len(self.discovered_urls)
            self.metrics['sources_succeeded'] = len(self.urls_by_source)
            self.metrics['sources_failed'] = len(self.failed_sources)
            self.metrics['elapsed_seconds'] = self.metrics['end_time'] - self.metrics['start_time']
            
            self._log_statistics()
            
            return {
                'total_urls': len(self.discovered_urls),
                'sources_succeeded': len(self.urls_by_source),
                'sources_failed': len(self.failed_sources),
                'elapsed_seconds': self.metrics['elapsed_seconds'],
                'urls_by_source': self.urls_by_source,
                'failed_sources': self.failed_sources,
            }
            
        except Exception as e:
            logger.error(f"[{self.correlation_id}] ✗ Seeding failed: {e}", exc_info=True)
            raise
    
    async def _seed_domain(
        self,
        seeder: AsyncUrlSeeder,
        domain: str,
        source_config: Dict[str, Any],
        current: int,
        total: int,
    ) -> None:
        """Seed single domain."""
        log_prefix = f"[{self.correlation_id}] [{current:3d}/{total:3d}]"
        
        logger.info(f"{log_prefix} {domain}")
        logger.info(f"       Est: {source_config.get('urls_estimate', 0):,} | Priority: {source_config.get('priority')} | Rep: {source_config.get('reputation')}")
        
        try:
            config = self._build_seeding_config(domain, source_config)
            
            logger.info(f"       Discovering...")
            urls_data = await asyncio.wait_for(
                seeder.urls(domain, config),
                timeout=300.0
            )
            
            if not urls_data:
                logger.warning(f"       ⊘ No URLs found")
                self.urls_by_source[domain] = []
                return
            
            candidate_urls = []
            for url_entry in urls_data:
                candidate_urls.append(
                    url_entry.get('url', '') if isinstance(url_entry, dict) else str(url_entry)
                )
            before = len(self.discovered_urls)
            self.add_crawl_domain(domain, candidate_urls)
            valid_urls = self.urls_by_source.get(domain, [])
            newly_added = len(self.discovered_urls) - before
            self.source_metrics[domain] = {
                'urls_discovered': len(valid_urls),
                'estimated_urls': source_config.get('urls_estimate', 0),
                'source_type': source_config.get('source_type', ''),
            }
            
            logger.info(f"       ✓ {len(valid_urls):,} URLs discovered")
            
        except asyncio.TimeoutError:
            logger.error(f"       ✗ Timeout")
            self.failed_sources.append({
                'domain': domain,
                'error': 'Timeout',
                'timestamp': datetime.now().isoformat(),
            })
        except Exception as e:
            logger.error(f"       ✗ {str(e)}")
            self.failed_sources.append({
                'domain': domain,
                'error': str(e),
                'timestamp': datetime.now().isoformat(),
            })
    
    def _log_statistics(self) -> None:
        """Log detailed statistics."""
        elapsed = self.metrics.get('elapsed_seconds', 0)
        
        logger.info(f"\n{'='*90}")
        logger.info(f"[STATISTICS] Enterprise URL Seeding")
        logger.info(f"{'='*90}")
        logger.info(f"Total unique URLs discovered: {len(self.discovered_urls):,}")
        logger.info(f"Estimated total URLs: {self.metrics['total_urls_estimated']:,}")
        logger.info(f"Actual vs Estimated: {(len(self.discovered_urls) / self.metrics['total_urls_estimated'] * 100):.1f}%")
        logger.info(f"Sources succeeded: {self.metrics['sources_succeeded']}")
        logger.info(f"Sources failed: {self.metrics['sources_failed']}")
        logger.info(f"Time elapsed: {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
        if elapsed > 0:
            logger.info(f"Throughput: {len(self.discovered_urls) / elapsed:,.0f} URLs/sec")
        
        logger.info(f"\nTop 10 sources by URLs:")
        top_sources = sorted(
            self.source_metrics.items(),
            key=lambda x: x[1]['urls_discovered'],
            reverse=True
        )[:10]
        for domain, metrics in top_sources:
            logger.info(f"  {domain}: {metrics['urls_discovered']:,}")
        
        logger.info(f"{'='*90}\n")
    
    @staticmethod
    def normalize_url(url: str) -> str:
        """Return a stable URL form for deduplication and sitemap output."""
        parsed = urlsplit(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))

    def add_crawl_domain(self, domain: str, urls: List[str]) -> int:
        """Add crawlable URLs for a domain and return the number newly added."""
        normalized_domain = domain.strip().lower()
        added = 0
        records = self.urls_by_source.setdefault(normalized_domain, [])
        existing = {record["url"] for record in records}
        for raw_url in urls:
            url = self.normalize_url(raw_url)
            if not url or url in self.discovered_urls:
                continue
            self.discovered_urls.add(url)
            records.append({
                "url": url,
                "source": normalized_domain,
                "discovered_at": datetime.now().isoformat(),
            })
            added += 1
        self.source_metrics.setdefault(normalized_domain, {})["urls_discovered"] = len(records)
        return added

    def finalize_crawl_domain(self, filename: str = "master_seed.xml") -> str:
        """Finalize a crawl domain by writing the deduplicated master sitemap."""
        return self.save_master_sitemap_xml(filename)

    def save_master_sitemap_xml(self, filename: str = "master_seed.xml") -> str:
        """
        Generate master_seed.xml - The main sitemap for crawling.
        
        This is the key file used by the crawler.
        """
        output_path = Path(settings.BASE_DIR) / "data/raw/sitemap" / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        urlset = ET.Element('urlset')
        urlset.set('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9')
        urlset.set('xmlns:xhtml', 'http://www.w3.org/1999/xhtml')
        
        for url in sorted(self.discovered_urls):
            url_elem = ET.SubElement(urlset, 'url')
            
            loc = ET.SubElement(url_elem, 'loc')
            loc.text = url
            
            lastmod = ET.SubElement(url_elem, 'lastmod')
            lastmod.text = datetime.now().isoformat()
            
            changefreq = ET.SubElement(url_elem, 'changefreq')
            changefreq.text = 'weekly'
            
            priority = ET.SubElement(url_elem, 'priority')
            priority.text = '0.8'
        
        # Atomic write
        temp_fd, temp_path = tempfile.mkstemp(text=True, suffix='.xml')
        try:
            tree = ET.ElementTree(urlset)
            with os.fdopen(temp_fd, "wb") as temp_file:
                tree.write(temp_file, encoding="utf-8", xml_declaration=True)
            Path(temp_path).replace(output_path)
        except Exception:
            Path(temp_path).unlink(missing_ok=True)
            raise
        
        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        logger.info(f"✓ Generated master sitemap: {output_path}")
        logger.info(f"  Total URLs: {len(self.discovered_urls):,}")
        logger.info(f"  File size: {file_size_mb:.1f} MB")
        
        return str(output_path)
    
    def save_comprehensive_json(self, filename: str = "seeds.json") -> str:
        """Save comprehensive JSON index with all URLs and metadata."""
        output_path = Path(settings.BASE_DIR) / "data/raw/sitemap" / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            'metadata': {
                'total_urls': len(self.discovered_urls),
                'sources_succeeded': len(self.urls_by_source),
                'sources_failed': len(self.failed_sources),
                'discovered_at': datetime.now().isoformat(),
                'correlation_id': self.correlation_id,
                'estimated_urls': self.metrics['total_urls_estimated'],
                'elapsed_seconds': self.metrics.get('elapsed_seconds', 0),
                'throughput_urls_per_sec': len(self.discovered_urls) / max(1, self.metrics.get('elapsed_seconds', 1)),
            },
            'urls': sorted(list(self.discovered_urls)),
            'by_source': self.urls_by_source,
            'source_metrics': self.source_metrics,
            'failed_sources': self.failed_sources,
        }
        
        # Atomic write
        temp_fd, temp_path = tempfile.mkstemp(text=True, suffix='.json')
        try:
            with open(temp_fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            Path(temp_path).replace(output_path)
        finally:
            try:
                import os
                os.close(temp_fd)
            except:
                pass
        
        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        logger.info(f"✓ Generated seeds JSON: {output_path}")
        logger.info(f"  File size: {file_size_mb:.1f} MB")
        
        return str(output_path)


async def main():
    """Main entry point."""
    seeder = EnterpriseURLSeeder()
    
    # Seed all enterprise sources (2M+ URLs)
    logger.info("\nStarting enterprise-scale URL seeding for 2M+ URLs...")
    
    result = await seeder.seed_urls(
        source_domains=None,
        tier_mode="all"  # All sources
    )
    
    # Generate outputs
    logger.info("\nGenerating output files...")
    seeder.save_master_sitemap_xml("master_seed.xml")
    seeder.save_comprehensive_json("seeds.json")
    
    logger.info("\n" + "="*90)
    logger.info("✓ ENTERPRISE URL SEEDING COMPLETE")
    logger.info("="*90)
    logger.info(f"Total URLs discovered: {result['total_urls']:,}")
    logger.info(f"Output files:")
    logger.info(f"  • master_seed.xml - Use this for crawling")
    logger.info(f"  • seeds.json - Complete index")
    logger.info("="*90 + "\n")
    
    return result


if __name__ == "__main__":
    asyncio.run(main())
